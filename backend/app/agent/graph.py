import logging
import time
import uuid
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from app.agent import nodes
from app.agent.state import AgentState
from app.db import engine
from app.models import Issue
from app.utils.time import now_utc

logger = logging.getLogger(__name__)


def _checkpoint_meta(issue_id: str, meta: dict[str, Any]) -> None:
    """Flush the current in-memory meta snapshot to issues.drafts_json.
    Writes are best-effort; a DB hiccup mid-run must not kill the agent.

    This is what drives the live generation dashboard. The finalize node
    still writes the authoritative drafts_json at the end; this merges
    the live meta over whatever is there so partial state (current_node,
    completed_nodes, timings so far, drop_trace so far) shows up in the UI
    while the run is still in flight."""
    try:
        with Session(engine) as s:
            issue = s.get(Issue, uuid.UUID(issue_id))
            if issue is None:
                return
            existing = dict(issue.drafts_json or {})
            existing["meta"] = dict(meta)
            issue.drafts_json = existing
            s.add(issue)
            s.commit()
    except Exception:
        logger.exception("checkpoint_meta failed for issue %s", issue_id)


def _timed(name: str, fn):
    """Wrap a node so its wall-clock duration lands in state.meta.timings
    and the whole meta snapshot checkpoints to the DB at node boundaries.

    At entry: record current_node + node_started_at and checkpoint so the
    UI sees which step is running.
    At exit:  record timing + append to completed_nodes and checkpoint
    again so the UI catches progress even if the next node is slow."""

    async def wrapper(state: AgentState) -> AgentState:
        issue_id = state.get("issue_id") if isinstance(state, dict) else None
        meta_in = state.setdefault("meta", {}) if isinstance(state, dict) else {}
        if issue_id:
            meta_in["current_node"] = name
            meta_in.setdefault("node_started_at", {})[name] = now_utc().isoformat()
            _checkpoint_meta(issue_id, meta_in)

        t0 = time.perf_counter()
        result = await fn(state)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if isinstance(result, dict):
            meta = result.setdefault("meta", {})
            meta.setdefault("timings", {})[name] = elapsed_ms
            completed = meta.setdefault("completed_nodes", [])
            if name not in completed:
                completed.append(name)
            # Clear current_node when render finishes; otherwise the next
            # node's entry wrapper will overwrite it.
            if name == "render":
                meta["current_node"] = None
            if issue_id:
                _checkpoint_meta(issue_id, meta)
        return result

    wrapper.__name__ = f"timed_{name}"
    return wrapper


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("ingest_rss", _timed("ingest_rss", nodes.ingest_rss))
    g.add_node("ingest_search", _timed("ingest_search", nodes.ingest_search))
    g.add_node("embed", _timed("embed", nodes.embed))
    g.add_node("dedupe", _timed("dedupe", nodes.dedupe))
    g.add_node("select", _timed("select", nodes.select_stories))
    g.add_node("draft", _timed("draft", nodes.draft))
    g.add_node("critique", _timed("critique", nodes.critique))
    g.add_node("editorial", _timed("editorial", nodes.editorial))
    g.add_node("puzzles", _timed("puzzles", nodes.puzzles))
    g.add_node("finalize", _timed("finalize", nodes.finalize))
    g.add_node("render", _timed("render", nodes.render))

    g.add_edge(START, "ingest_rss")
    g.add_edge("ingest_rss", "ingest_search")
    g.add_edge("ingest_search", "embed")
    g.add_edge("embed", "dedupe")
    g.add_edge("dedupe", "select")
    g.add_edge("select", "draft")
    g.add_edge("draft", "critique")
    g.add_edge("critique", "editorial")
    g.add_edge("editorial", "puzzles")
    g.add_edge("puzzles", "finalize")
    g.add_edge("finalize", "render")
    g.add_edge("render", END)

    return g


@lru_cache(maxsize=1)
def get_graph():
    return _build_graph().compile()
