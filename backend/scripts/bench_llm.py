"""Benchmark the configured chat LLM across three call shapes.

Mirrors the methodology from docs/reports/litellm-function-calling-hang.md:
plain chat, JSON mode, and structured output (native tool calling on Ollama,
function_calling on the OpenAI-compat path). Uses the same ~10-candidate
SELECT prompt that the real agent runs, so timings reflect real workload.

Run inside the backend container:

    docker compose exec backend python -m scripts.bench_llm
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.llm import _using_ollama, get_chat_llm, get_structured_llm
from app.agent.prompts import SELECT_INSTRUCTION, SYSTEM_PROMPT
from app.config import settings

TIMEOUT_SECONDS = 300


class _SelectOutput(BaseModel):
    keep_ids: list[str] = Field(default_factory=list)
    lead_id: Optional[str] = None


CANDIDATES = [
    (
        "cand-01",
        "Silver Falls Season 3 premieres July 3",
        "Brackish Studio confirmed the third season of Silver Falls will debut July 3, 2026 on Horizon+ and Archive Streaming simultaneously.",
    ),
    (
        "cand-02",
        "Foundry comic takes a 3-week break",
        "The author will pause Foundry for three weeks starting this issue of Weekly Current.",
    ),
    (
        "cand-03",
        "Prism Deluxe getting 4K re-release bonus card",
        "The publisher announces a limited edition 4K UHD with an exclusive collector's card.",
    ),
    (
        "cand-04",
        "Night Garden hits theaters April 25",
        "The studio confirmed the film's opening date domestically; streaming debut to follow in May.",
    ),
    (
        "cand-05",
        "Top 10 best show endings of all time — you won't believe #3",
        "SEO roundup of opinion rankings, no new information.",
    ),
    (
        "cand-06",
        "Foundry spinoff comic announced",
        "New spinoff written by the author's assistant, no release date yet.",
    ),
    (
        "cand-07",
        "The Long Night wins Show of the Year at industry awards",
        "The annual awards ceremony named The Long Night best show over Deep Field.",
    ),
    (
        "cand-08",
        "Deep Field Part 2 chapter 180 trailer released",
        "Short teaser trailer dropped on the official social account, no release date changes.",
    ),
    (
        "cand-09",
        "Silver Falls dub episode 72 airs May 10",
        "Horizon+ confirmed the English dub airs May 10, 2026.",
    ),
    (
        "cand-10",
        "Studio's next film rumored for 2027",
        "Rumor sourced from a single blog post citing an anonymous insider at the studio.",
    ),
]


def render_prompt() -> tuple[str, str]:
    lines = "\n".join(
        f"- id={cid} title={title!r} summary={summary!r}" for cid, title, summary in CANDIDATES
    )
    user = SELECT_INSTRUCTION.format(topic_name="Shows & Films") + "\n\nCandidates:\n" + lines
    return SYSTEM_PROMPT, user


async def _run(label: str, llm, messages) -> None:
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(llm.ainvoke(messages), timeout=TIMEOUT_SECONDS)
        elapsed = time.perf_counter() - t0
        preview = (
            str(result.model_dump())
            if hasattr(result, "model_dump")
            else getattr(result, "content", str(result))
        )[:220]
        print(f"{label:<22} OK  in {elapsed:6.1f}s  :: {preview}")
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        print(f"{label:<22} TIMEOUT after {elapsed:.1f}s")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"{label:<22} ERROR in {elapsed:.1f}s :: {type(exc).__name__}: {str(exc)[:200]}")


async def main() -> None:
    mode = "ollama" if _using_ollama() else "openai-compat"
    model = settings.ollama_model if _using_ollama() else settings.openai_model
    base = settings.ollama_api_base if _using_ollama() else settings.openai_api_base
    print(f"mode={mode} model={model} base={base} timeout={TIMEOUT_SECONDS}s")
    print("-" * 72)

    system, user = render_prompt()
    messages = [SystemMessage(content=system), HumanMessage(content=user)]

    plain_llm = get_chat_llm()
    await _run("plain chat", plain_llm, messages)

    if _using_ollama():
        json_llm = plain_llm.bind(format="json")
    else:
        json_llm = plain_llm.bind(response_format={"type": "json_object"})
    await _run("json mode", json_llm, messages)

    structured_llm = get_structured_llm(_SelectOutput, temperature=0)
    await _run("structured (tools)", structured_llm, messages)


if __name__ == "__main__":
    asyncio.run(main())
