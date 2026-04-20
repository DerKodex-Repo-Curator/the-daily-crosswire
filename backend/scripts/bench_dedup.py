"""Labeled benchmark for the intra-topic dedup pass (LLM first + embedding
safety net), as it now runs inside select_stories.

Goal: exercise three failure modes the previous design hit:
  1. Real same-event dupes across outlets that title-only embeddings can't
     separate (paraphrased Spanish headlines clustered at 0.60-0.85).
  2. Aggregator / social-media handle pages acting as a 'black hole':
     greedy embedding pass was dropping concrete incident reports in
     favor of keeping the aggregator because the aggregator was early in
     the keep list.
  3. Distinct items sharing an entity that should stay separate.

Scoring:
  - precision: of the items the pipeline dropped, how many were really dupes?
  - recall:    of the real dupes, how many did we drop?
  - representative correctness: inside each cluster, did we keep the best
    representative (not the aggregator)?

Run inside the backend container:

    docker compose exec backend python -m scripts.bench_dedup
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import _using_ollama, get_structured_llm
from app.agent.nodes import (
    _DedupOutput,
    _content_text_for_dedup,
    _cosine,
    _invoke_with_parse_retry,
)
from app.agent import prompts
from app.config import settings
from app.services import embeddings as emb_service


@dataclass
class LabeledItem:
    id: str
    title: str
    summary: str
    cluster: str  # "unique" or a cluster label shared by dupes
    is_best_of_cluster: bool  # True for the preferred representative


# ---------------------------------------------------------------------------
# Labeled fixture. Mix of same-event dupe clusters, aggregator pollution,
# and distinct stories. Fictional Gotham + local outlets.

ITEMS: list[LabeledItem] = [
    # Cluster A: four outlets covering illegal dumping in Brewer Park (one event)
    LabeledItem(
        "dumping-gazette",
        "Authorities step up 24/7 patrols against illegal dumping in Brewer Park",
        "The regional authority announced continuous patrols in Brewer Park after a fresh spike of illegal dumping was detected in the upper ridge.",
        cluster="dumping",
        is_best_of_cluster=True,  # mainstream outlet, specific operational detail
    ),
    LabeledItem(
        "dumping-metro",
        "Illegal dumping with out-of-state haulers threatens Brewer Park in Gotham",
        "Metro Beat reports the use of out-of-state hauler trucks by illegal groups in the clandestine dump sites of Brewer Park.",
        cluster="dumping",
        is_best_of_cluster=False,
    ),
    LabeledItem(
        "dumping-herald",
        "New illegal dump found in Brewer Park: city's response",
        "The Herald reports the discovery of a new illegal dump inside Brewer Park and describes the institutional response.",
        cluster="dumping",
        is_best_of_cluster=False,
    ),
    LabeledItem(
        "dumping-ig",
        "Illegal dumping sets off alarms again in Brewer Park",
        "Instagram post from the local newspaper warning about renewed illegal dumping in Brewer Park.",
        cluster="dumping",
        is_best_of_cluster=False,
    ),
    # Cluster B: three framings of the same water/turbidity incident
    LabeledItem(
        "water-gazette",
        "Metro Water trucks supply neighborhoods hit by service cut",
        "Metro Water deployed tanker trucks across several neighborhoods after the service was cut due to high turbidity in the Hudson River, per the Gotham Gazette.",
        cluster="water-cut",
        is_best_of_cluster=True,
    ),
    LabeledItem(
        "water-ig1",
        "GOTHAM | Historic turbidity levels on the Hudson River",
        "Instagram post reporting record turbidity on the Hudson River that forced suspension of pumping at the Riverside treatment plant.",
        cluster="water-cut",
        is_best_of_cluster=False,
    ),
    LabeledItem(
        "water-fb",
        "GOTHAM ALERT. Turbidity spike on the river registered",
        "Facebook group post warning of a turbidity spike on the Hudson River and possible water service cuts.",
        cluster="water-cut",
        is_best_of_cluster=False,
    ),
    # Aggregator pollution (same topic, no specific incident) should cluster
    # with SOMETHING or be dropped, but MUST NOT be picked as representative.
    LabeledItem(
        "agg-metrobeat",
        "Metro Beat Gotham (@MetroBeatGTH) / Posts / X",
        "Official X profile of the regional outlet Metro Beat Gotham. Recent posts cover citywide news.",
        cluster="unique-agg",  # on its own: the pipeline should drop it as junk
        is_best_of_cluster=False,
    ),
    # Genuinely distinct incidents: should NOT be dropped
    LabeledItem(
        "accident-main3rd",
        "Accident on Main Street and 3rd Avenue — Downtown Gotham",
        "Traffic accident reported at Main Street and 3rd Avenue, Downtown Gotham. Slow traffic in the area.",
        cluster="unique-accident",
        is_best_of_cluster=True,
    ),
    LabeledItem(
        "homicide-8thbridge",
        "Homicide reported on 8th Avenue and Bridge Street",
        "Homicide reported in the early morning at the intersection of 8th Avenue and Bridge Street. Authorities investigating.",
        cluster="unique-homicide",
        is_best_of_cluster=True,
    ),
]


def _score(drop_ids: set[str], kept_ids: set[str]) -> dict:
    dupes_gt = {
        i.id
        for i in ITEMS
        if i.cluster.startswith(("dumping", "water-cut")) and not i.is_best_of_cluster
    }
    # Aggregator alone in its cluster: treated as "should be dropped" too
    dupes_gt |= {i.id for i in ITEMS if i.cluster == "unique-agg"}
    distinct_gt = {i.id for i in ITEMS if i.id not in dupes_gt}

    tp = len(drop_ids & dupes_gt)
    fp = len(drop_ids & distinct_gt)
    fn = len(dupes_gt - drop_ids)
    tn = len(distinct_gt - drop_ids)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    # Representative correctness: for each known dup cluster that has any
    # representative still kept, did we keep the is_best one?
    rep_ok = 0
    rep_total = 0
    for cluster in {"dumping", "water-cut"}:
        members = [i for i in ITEMS if i.cluster == cluster]
        kept_members = [i for i in members if i.id in kept_ids]
        if not kept_members:
            continue
        rep_total += 1
        if any(i.is_best_of_cluster for i in kept_members):
            rep_ok += 1
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "rep_ok": rep_ok,
        "rep_total": rep_total,
    }


async def _llm_pass(topic_name: str, items: list[LabeledItem]) -> list[str]:
    llm = get_structured_llm(_DedupOutput, temperature=0)
    lines = []
    for it in items:
        lines.append(f"- id={it.id}  title={it.title!r}  summary={it.summary[:200]!r}")
    user_msg = (
        prompts.DEDUP_INSTRUCTION.format(topic_name=topic_name) + "\n\nItems:\n" + "\n".join(lines)
    )
    result = await _invoke_with_parse_retry(
        llm,
        [
            SystemMessage(content=prompts.SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ],
    )
    valid = {i.id for i in items}
    return [str(x) for x in (result.drop_ids or []) if str(x) in valid]


async def _emb_pass(items: list[LabeledItem], threshold: float) -> list[tuple[str, str, float]]:
    """Greedy walk matching _collapse_similar_embeddings. Returns dropped list
    (dropped_id, kept_id, sim)."""
    texts = [_content_text_for_dedup(i.title, i.summary) for i in items]
    vecs = await emb_service.embed(texts)
    kept_vecs: list[tuple[str, list[float]]] = []
    dropped: list[tuple[str, str, float]] = []
    for it, vec in zip(items, vecs):
        matched: Optional[tuple[str, float]] = None
        for kept_id, kv in kept_vecs:
            sim = _cosine(vec, kv)
            if sim >= threshold and (matched is None or sim > matched[1]):
                matched = (kept_id, sim)
        if matched is not None:
            dropped.append((it.id, matched[0], matched[1]))
        else:
            kept_vecs.append((it.id, vec))
    return dropped


async def main() -> None:
    mode = "ollama" if _using_ollama() else "openai-compat"
    model = settings.ollama_model if _using_ollama() else settings.openai_model
    threshold = settings.select_intra_sim_threshold
    topic = "Gotham"

    print(f"mode={mode}  model={model}  intra_threshold={threshold}")
    print(
        f"items={len(ITEMS)}  clusters=dumping(4) water-cut(3) unique-agg(1) unique-accident(1) unique-homicide(1)"
    )
    print("-" * 72)

    all_ids = {i.id for i in ITEMS}
    drop_ids: set[str] = set()

    # LLM pass
    t0 = time.perf_counter()
    llm_drops = await _llm_pass(topic, ITEMS)
    print(f"\n[LLM pass] {time.perf_counter()-t0:.1f}s")
    print(f"  dropped ({len(llm_drops)}): {llm_drops}")
    drop_ids |= set(llm_drops)

    # Emb safety net on survivors
    survivors = [i for i in ITEMS if i.id not in drop_ids]
    t0 = time.perf_counter()
    emb_drops = await _emb_pass(survivors, threshold)
    print(f"\n[EMB pass] {time.perf_counter()-t0:.1f}s  (on {len(survivors)} survivors)")
    for d, k, s in emb_drops:
        print(f"  {d}  drops-to  {k}  sim={s:.3f}")
    drop_ids |= {d for (d, _, _) in emb_drops}

    kept_ids = all_ids - drop_ids
    m = _score(drop_ids, kept_ids)
    print("\n=== RESULTS ===")
    print(f"  kept ({len(kept_ids)}): {sorted(kept_ids)}")
    print(f"  dropped ({len(drop_ids)}): {sorted(drop_ids)}")
    print(
        f"  P={m['precision']:.2f}  R={m['recall']:.2f}  F1={m['f1']:.2f}  "
        f"(tp={m['tp']} fp={m['fp']} fn={m['fn']} tn={m['tn']})"
    )
    print(
        f"  representative correctness: {m['rep_ok']}/{m['rep_total']} clusters "
        f"kept the best item as the survivor"
    )

    by_id = {i.id: i for i in ITEMS}
    wrong_drops = [i for i in drop_ids if by_id[i].is_best_of_cluster]
    if wrong_drops:
        print("\n  WRONG DROPS (kept a worse representative):")
        for i in wrong_drops:
            print(f"    - {i}: {by_id[i].title}")


if __name__ == "__main__":
    asyncio.run(main())
