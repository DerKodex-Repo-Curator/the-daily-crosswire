"""Validate that qwen3:14b handles the extended _SelectOutput schema
with a `drop_reasons: Optional[dict[str, str]]` field WITHOUT degrading
speed or selection quality.

Baseline comparison:
  - The existing `_SelectOutput { keep_ids, lead_id }` (flat, qwen3:14b-proven)
  - This extended `{ keep_ids, lead_id, drop_reasons }` (one more flat dict field)

The dict-of-strings shape is the same region the model has been handling
cleanly for select and dedup passes. If it holds here, we wire it in;
if it times out or loses keep-decision stability, we abandon and stick
with structural metadata only.

Reuses the two hand-labeled batches from bench_select_quality.py so scoring
is directly comparable.

Run inside the backend container:

    docker compose exec backend python -m scripts.bench_select_reasons
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.llm import _using_ollama, get_structured_llm
from app.agent.prompts import SELECT_INSTRUCTION, SYSTEM_PROMPT
from app.config import settings
from scripts.bench_select_quality import ENT_BATCH, LOC_BATCH, LabeledItem

TIMEOUT_SECONDS = 300


class _SelectOutputBaseline(BaseModel):
    keep_ids: list[str] = Field(default_factory=list)
    lead_id: Optional[str] = None


class _SelectOutputWithReasons(BaseModel):
    keep_ids: list[str] = Field(
        default_factory=list,
        description="news_item_ids to keep, best-first.",
    )
    lead_id: Optional[str] = Field(
        default=None,
        description="id from keep_ids to feature as the topic's lead, or null.",
    )
    drop_reasons: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of news_item_id -> short one-line reason (under 80 chars) "
            "for every candidate NOT in keep_ids. Example: "
            "{'abc-1': 'trailer-only, no near-term release', 'abc-2': 'merch/promo card'}"
        ),
    )


REASONS_RUBRIC_TAIL = """

Also return `drop_reasons`: for every candidate you did NOT keep, add a
short (under 80 characters) reason to the map keyed by the candidate's
id. One line per item, the specific rule from above that caused the
drop (e.g. "trailer-only, no near-term release", "merch/promo card",
"aggregator profile, no concrete incident", "duplicate of an earlier
item"). Keep reasons factual and mechanical, not editorial.
"""


def _render_prompt(topic_name: str, items: list[LabeledItem]) -> tuple[str, str]:
    lines = "\n".join(
        f"- id={it.id}  title={it.title!r}  source={it.source!r}  summary={it.summary!r}"
        for it in items
    )
    user = (
        SELECT_INSTRUCTION.format(topic_name=topic_name)
        + REASONS_RUBRIC_TAIL
        + "\n\nCandidates:\n"
        + lines
    )
    return SYSTEM_PROMPT, user


def _score(items: list[LabeledItem], kept_ids: set[str]) -> dict:
    tp = sum(1 for it in items if it.expect_keep and it.id in kept_ids)
    fp = sum(1 for it in items if not it.expect_keep and it.id in kept_ids)
    fn = sum(1 for it in items if it.expect_keep and it.id not in kept_ids)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


async def _run(
    label: str,
    topic: str,
    items: list[LabeledItem],
    schema,
    include_reasons_rubric: bool,
) -> dict:
    if include_reasons_rubric:
        system, user = _render_prompt(topic, items)
    else:
        lines = "\n".join(
            f"- id={it.id}  title={it.title!r}  source={it.source!r}  summary={it.summary!r}"
            for it in items
        )
        user = SELECT_INSTRUCTION.format(topic_name=topic) + "\n\nCandidates:\n" + lines
        system = SYSTEM_PROMPT

    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    llm = get_structured_llm(schema, temperature=0)

    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(llm.ainvoke(messages), timeout=TIMEOUT_SECONDS)
        elapsed = time.perf_counter() - t0
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        print(f"  {label}: TIMEOUT after {elapsed:.1f}s")
        return {"ok": False, "elapsed": elapsed}
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"  {label}: ERROR in {elapsed:.1f}s :: {type(exc).__name__}: {str(exc)[:200]}")
        return {"ok": False, "elapsed": elapsed}

    kept = [str(x) for x in (result.keep_ids or [])]
    kept_set = set(kept)
    metrics = _score(items, kept_set)

    out = {
        "ok": True,
        "elapsed": elapsed,
        "kept": kept,
        "lead_id": getattr(result, "lead_id", None),
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
    }
    if hasattr(result, "drop_reasons"):
        reasons = dict(result.drop_reasons or {})
        all_ids = {it.id for it in items}
        dropped = all_ids - kept_set
        missing = dropped - set(reasons.keys())
        unexpected = set(reasons.keys()) - all_ids
        empty = [k for k, v in reasons.items() if not (v or "").strip()]
        out["drop_reasons"] = reasons
        out["missing_reasons"] = sorted(missing)
        out["unexpected_reason_ids"] = sorted(unexpected)
        out["empty_reasons"] = sorted(empty)
    return out


def _summary(label: str, r: dict) -> None:
    if not r.get("ok"):
        return
    print(
        f"  {label}: {r['elapsed']:.1f}s   "
        f"kept={r['kept']}   "
        f"lead={r['lead_id']}   "
        f"P={r['precision']:.2f} R={r['recall']:.2f} F1={r['f1']:.2f}"
    )
    if "drop_reasons" in r:
        print(
            f"    reasons={len(r['drop_reasons'])}  "
            f"missing={len(r['missing_reasons'])}  "
            f"empty={len(r['empty_reasons'])}  "
            f"unexpected={len(r['unexpected_reason_ids'])}"
        )
        for rid, reason in r["drop_reasons"].items():
            print(f"      - {rid}: {reason[:80]}")
        if r["missing_reasons"]:
            print(f"    MISSING REASONS (dropped but no reason given): {r['missing_reasons']}")


async def main() -> None:
    mode = "ollama" if _using_ollama() else "openai-compat"
    model = settings.ollama_model if _using_ollama() else settings.openai_model
    print(f"mode={mode}  model={model}  timeout={TIMEOUT_SECONDS}s")
    print("=" * 72)

    for label, topic, batch in [
        ("ENT", "Shows & Films", ENT_BATCH),
        ("LOC", "Gotham", LOC_BATCH),
    ]:
        print(f"\n[{label}] topic={topic!r}  n={len(batch)}")
        print("-" * 60)

        baseline = await _run(
            f"baseline  {label}", topic, batch, _SelectOutputBaseline, include_reasons_rubric=False
        )
        _summary(f"baseline  {label}", baseline)

        extended = await _run(
            f"w/reasons {label}",
            topic,
            batch,
            _SelectOutputWithReasons,
            include_reasons_rubric=True,
        )
        _summary(f"w/reasons {label}", extended)

        if baseline.get("ok") and extended.get("ok"):
            delta_s = extended["elapsed"] - baseline["elapsed"]
            pct = 100 * delta_s / baseline["elapsed"] if baseline["elapsed"] else 0
            f1_delta = extended["f1"] - baseline["f1"]
            print(f"  DELTA: +{delta_s:.1f}s ({pct:+.0f}%)  F1 shift: {f1_delta:+.2f}")


if __name__ == "__main__":
    asyncio.run(main())
