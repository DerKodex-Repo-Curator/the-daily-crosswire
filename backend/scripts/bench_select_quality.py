"""Labeled quality benchmark for the SELECT node.

Runs SELECT_INSTRUCTION against two hand-labeled batches (one entertainment,
one local-city) and scores the LLM's picks against expected keep/drop labels.
Reports precision / recall / F1 and flags false positives + false negatives
by title so prompt iteration has a concrete target.

Run inside the backend container:

    docker compose exec backend python -m scripts.bench_select_quality
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.llm import _using_ollama, get_structured_llm
from app.agent.prompts import SELECT_INSTRUCTION, SYSTEM_PROMPT
from app.config import settings

TIMEOUT_SECONDS = 300


class _SelectOutput(BaseModel):
    keep_ids: list[str] = Field(default_factory=list)
    lead_id: Optional[str] = None


@dataclass
class LabeledItem:
    id: str
    title: str
    source: str
    summary: str
    expect_keep: bool
    note: str = ""


ENT_BATCH: list[LabeledItem] = [
    LabeledItem(
        "ent-01",
        "Silver Falls Season 3 Premieres May 22",
        "showwire.example",
        "The third season of Silver Falls premieres on May 22, following the current storyline's conclusion.",
        expect_keep=True,
        note="new season premiere, specific near-term date",
    ),
    LabeledItem(
        "ent-02",
        "The Long Night Season 2 Premieres July 3 on Horizon+",
        "showwire.example",
        "Horizon+ confirmed the second season of The Long Night will debut July 3, 2026.",
        expect_keep=True,
        note="new season premiere with concrete date ~2.5 months out; borderline",
    ),
    LabeledItem(
        "ent-03",
        "Deep Field Reveals Gameplay Trailer",
        "showwire.example",
        "Brackish Studio posted a gameplay trailer for Deep Field ahead of its July 10 launch.",
        expect_keep=False,
        note="trailer reveal is marketing, not news",
    ),
    LabeledItem(
        "ent-04",
        "Fortress DLC Release Celebrates Game's Anniversary",
        "showwire.example",
        "A trailer for Fortress revealed a DLC release date for the Scout on April 24, tied to the game's anniversary.",
        expect_keep=False,
        note="DLC anniversary; explicit drop",
    ),
    LabeledItem(
        "ent-05",
        "Prism Streams First 11 Minutes of Upcoming Film",
        "showwire.example",
        "The animated feature Prism released its first 11 minutes online ahead of its March 13 premiere.",
        expect_keep=False,
        note="first-N-minutes preview clip",
    ),
    LabeledItem(
        "ent-06",
        "Foundry Reveals English Dub Cast",
        "showwire.example",
        "The show adaptation of the novel series Foundry announced its English dub cast.",
        expect_keep=False,
        note="dub cast reveal, no release news",
    ),
    LabeledItem(
        "ent-07",
        "Archive Streaming Adds Crimson Film in May",
        "showwire.example",
        "Archive Streaming will add the 2011 film Crimson to its catalog in May.",
        expect_keep=False,
        note="older film added to streaming catalog",
    ),
    LabeledItem(
        "ent-08",
        "Sable Handheld Returns with Hardware-Based Console",
        "showwire.example",
        "Sable announced a hardware-based revival of its classic handheld console.",
        expect_keep=False,
        note="retro hardware revival",
    ),
    LabeledItem(
        "ent-09",
        "Deep Field Wins Industry Award for Narrative Design",
        "showwire.example",
        "Deep Field won the Narrative Design prize at this year's industry awards.",
        expect_keep=False,
        note="award win, not a release",
    ),
    LabeledItem(
        "ent-10",
        "Night Garden Opens April 25 in Theaters",
        "showwire.example",
        "The studio confirmed the film Night Garden opens in theaters April 25; streaming debut in May.",
        expect_keep=True,
        note="original film opening, concrete near-term date",
    ),
]


LOC_BATCH: list[LabeledItem] = [
    LabeledItem(
        "loc-01",
        "Accident on Main Street and 3rd Avenue — Downtown Gotham",
        "facebook.com/groups/gothamalerts",
        "Traffic accident reported this morning at Main Street and 3rd Avenue, Downtown Gotham.",
        expect_keep=True,
        note="concrete incident, specific location; social exception applies",
    ),
    LabeledItem(
        "loc-02",
        "GOTHAM | Homicide Reported on 8th Avenue and Bridge Street",
        "instagram.com",
        "Homicide reported at 8th Avenue and Bridge Street in Gotham during the early morning hours.",
        expect_keep=True,
        note="concrete crime, specific location; social exception applies",
    ),
    LabeledItem(
        "loc-03",
        "Hudson River Water Turbidity Hits Record High, Gotham Reservoir Alert",
        "instagram.com",
        "Hudson River turbidity recorded record levels overnight, forcing Metro Water to suspend pumping at the Riverside treatment plant.",
        expect_keep=True,
        note="water-supply public-health alert, specific river; social exception applies",
    ),
    LabeledItem(
        "loc-04",
        "Illegal Dumping Returns to Brewer Park, Prompts City Response",
        "gothamgazette.example",
        "Authorities report a new surge of illegal dumping in Brewer Park, with enforcement teams on site.",
        expect_keep=True,
        note="local environmental incident, mainstream outlet",
    ),
    LabeledItem(
        "loc-05",
        "Gotham - Wikipedia",
        "en.wikipedia.org",
        "Gotham is a major city in the northeastern region, with a population of approximately 7.2 million.",
        expect_keep=False,
        note="encyclopedia page",
    ),
    LabeledItem(
        "loc-06",
        "City Ombudsman Intervenes After Complaint",
        "gothamgazette.example",
        "The Gotham Ombudsman's office intervenes following a public complaint — details pending.",
        expect_keep=False,
        note="vague institutional action, no concrete scope",
    ),
    LabeledItem(
        "loc-07",
        "Gotham Advances Environmental and Infrastructure Projects",
        "gotham.gov.example",
        "Gotham City Hall highlights progress on environmental and infrastructure initiatives.",
        expect_keep=False,
        note="puff-piece municipal PR",
    ),
    LabeledItem(
        "loc-08",
        "Mayor Thompson's Public Image Under Fire in New Reel",
        "instagram.com",
        "Instagram reel of opinion commentary on the Gotham mayor's public standing.",
        expect_keep=False,
        note="social-media opinion, no concrete incident",
    ),
    LabeledItem(
        "loc-09",
        "Gotham Alerts — News Aggregator (@GothamAlerts) / Posts / X",
        "x.com",
        "X profile of the Gotham Alerts local news aggregator.",
        expect_keep=False,
        note="social-media aggregator account page",
    ),
    LabeledItem(
        "loc-10",
        "National Football League Standings — Week 9",
        "scores.example",
        "Week 9 standings for the National Football League.",
        expect_keep=False,
        note="sports standings, not Gotham-specific incident",
    ),
]


def _render_prompt(topic_name: str, items: list[LabeledItem]) -> tuple[str, str]:
    lines = "\n".join(
        f"- id={it.id}  title={it.title!r}  source={it.source!r}  summary={it.summary!r}"
        for it in items
    )
    user = SELECT_INSTRUCTION.format(topic_name=topic_name) + "\n\nCandidates:\n" + lines
    return SYSTEM_PROMPT, user


def _score(items: list[LabeledItem], kept_ids: set[str]) -> dict:
    tp = sum(1 for it in items if it.expect_keep and it.id in kept_ids)
    fp = sum(1 for it in items if not it.expect_keep and it.id in kept_ids)
    fn = sum(1 for it in items if it.expect_keep and it.id not in kept_ids)
    tn = sum(1 for it in items if not it.expect_keep and it.id not in kept_ids)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


async def _run_batch(label: str, topic: str, items: list[LabeledItem]) -> None:
    system, user = _render_prompt(topic, items)
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    llm = get_structured_llm(_SelectOutput, temperature=0)

    t0 = time.perf_counter()
    try:
        result: _SelectOutput = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        print(f"\n=== {label} ({topic}) ===  TIMEOUT after {elapsed:.1f}s")
        return

    elapsed = time.perf_counter() - t0
    kept = [str(x) for x in (result.keep_ids or [])]
    kept_set = set(kept)
    metrics = _score(items, kept_set)
    by_id = {it.id: it for it in items}
    expected_keep = [it.id for it in items if it.expect_keep]

    print(f"\n=== {label} ({topic}) === {elapsed:.1f}s")
    print(f"  LLM kept ({len(kept)}): {kept}")
    print(f"  lead_id: {result.lead_id}")
    print(f"  expected keep ({len(expected_keep)}): {expected_keep}")
    print(
        f"  P={metrics['precision']:.2f}  R={metrics['recall']:.2f}  "
        f"F1={metrics['f1']:.2f}  (tp={metrics['tp']} fp={metrics['fp']} "
        f"fn={metrics['fn']} tn={metrics['tn']})"
    )

    fps = [by_id[i] for i in kept if i in by_id and not by_id[i].expect_keep]
    fns = [it for it in items if it.expect_keep and it.id not in kept_set]
    if fps:
        print("  FALSE POSITIVES (junk kept):")
        for it in fps:
            print(f"    - [{it.id}] {it.title}  // {it.note}")
    if fns:
        print("  FALSE NEGATIVES (good dropped):")
        for it in fns:
            print(f"    - [{it.id}] {it.title}  // {it.note}")


async def main() -> None:
    mode = "ollama" if _using_ollama() else "openai-compat"
    model = settings.ollama_model if _using_ollama() else settings.openai_model
    print(
        f"mode={mode}  model={model}  "
        f"cap_per_batch={settings.select_max_kept_per_batch}  "
        f"timeout={TIMEOUT_SECONDS}s"
    )
    print("-" * 72)

    await _run_batch("ENT batch", "Shows & Films", ENT_BATCH)
    await _run_batch("LOC batch", "Gotham", LOC_BATCH)


if __name__ == "__main__":
    asyncio.run(main())
