"""Shared helper for flushing an in-memory meta snapshot to the issues row
mid-run. Lives in its own module so nodes can import it without pulling in
graph.py (which imports from nodes.py, so any reverse import would cycle).

Used by:
- graph.py::_timed, at each node's entry and exit
- nodes.py inside long LLM-heavy nodes (select, draft, critique, editorial)
  at sub-step boundaries, so the live dashboard sees per-topic / per-story
  progress without waiting for the whole node to finish.

Writes are best-effort; a DB hiccup mid-run must not kill the agent.
"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import Any

from sqlmodel import Session

from app.db import engine
from app.models import Issue

logger = logging.getLogger(__name__)


def checkpoint_meta(issue_id: str, meta: dict[str, Any]) -> None:
    """Flush the current meta snapshot into issues.drafts_json["meta"].

    Merges over whatever else is in drafts_json so partial state (current_node,
    completed_nodes, timings so far, drop_trace so far, per-node progress) shows
    up in the UI while the run is still in flight. The finalize node still
    writes the authoritative drafts_json at the end.

    Uses deepcopy so the persisted JSON doesn't share references with live
    agent state: if any future code path mutates `issue.drafts_json["meta"]`
    after this returns, it must not accidentally mutate the state dict the
    running graph is still writing to."""
    try:
        with Session(engine) as s:
            issue = s.get(Issue, uuid.UUID(issue_id))
            if issue is None:
                return
            existing = dict(issue.drafts_json or {})
            existing["meta"] = copy.deepcopy(meta)
            issue.drafts_json = existing
            s.add(issue)
            s.commit()
    except Exception:
        logger.exception("checkpoint_meta failed for issue %s", issue_id)
