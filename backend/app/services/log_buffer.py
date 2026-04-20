"""In-memory per-issue log buffer for the live-generation dashboard.

How it works:
- `set_current_issue(id)` is called from runner.run_issue() before the
  graph invokes. A ContextVar carries the issue id through async
  task-local context so any logger call inside the agent tags the entry
  with that id.
- `IssueLogHandler` is attached at app startup. Every log record that
  passes the signal/noise filter (_should_keep) lands in the buffer for
  the currently-active issue.
- `tail(issue_id, since)` returns entries newer than `since` for the UI
  to poll. Buffers TTL out 10 minutes after the last write so finished
  runs linger briefly (nice for "see what just happened") without
  leaking memory.

Scope cuts:
- In-memory only; a backend restart wipes the buffer. That's fine: a
  restart kills the in-flight generation anyway.
- One process. No multi-worker support.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

_MAX_ENTRIES = 500
_BUFFER_TTL_SECONDS = 600  # 10 minutes after last write

_current_issue: ContextVar[Optional[str]] = ContextVar("_current_issue", default=None)

# Each entry: {"ts": iso, "level": "INFO", "logger": "app.agent.nodes", "msg": "..."}
_BUFFERS: dict[str, deque] = {}
_LAST_WRITE: dict[str, float] = {}
_LOCK = threading.Lock()


# Regex to drop the loudest noise lines after formatting. uvicorn's
# access logger emits the HTTP method + path in its message body, which
# is the cheapest place to filter out frontend polls without touching the
# uvicorn logger config.
_NOISE_PATHS_RE = re.compile(
    r"(?:"
    r"(?:GET|POST|PATCH|DELETE|OPTIONS|PUT)\s+"
    r"/(?:api/(?:health|issues|configs|debug/scheduler)|static|ws|docs|openapi\.json)"
    r")"
)
_HTTPX_200_RE = re.compile(r"HTTP Request:.*\"HTTP/1\.\d\s+2\d{2}\s")

# Loggers whose output we always want when at the allowed level.
_SIGNAL_LOGGERS = (
    "app.agent",
    "app.services",
    "app.routers",
    "app.scheduler",
    "app.main",
)


def _should_keep(record: logging.LogRecord) -> bool:
    """Filter: keep signal, drop polling, healthcheck, and 200-OK noise."""
    # Always drop the uvicorn access log spam entirely; anything we'd care
    # about from uvicorn is at WARNING or above.
    if record.name.startswith("uvicorn"):
        return record.levelno >= logging.WARNING

    # httpx INFO is the 200 OK spam; keep WARNING+ only.
    if record.name.startswith("httpx"):
        return record.levelno >= logging.WARNING

    # WatchFiles / feedparser / other libs: warnings+ only.
    if not any(record.name.startswith(p) for p in _SIGNAL_LOGGERS):
        return record.levelno >= logging.WARNING

    # Signal loggers: INFO+ is fine, but drop path-matching polls if any
    # leak through (they occasionally do under misconfiguration).
    try:
        msg = record.getMessage()
    except Exception:
        msg = str(record.msg)
    if _NOISE_PATHS_RE.search(msg):
        return False
    if _HTTPX_200_RE.search(msg):
        return False
    return True


class IssueLogHandler(logging.Handler):
    """Appends matching log records to the buffer of whichever issue the
    current async task belongs to. Invisible when no issue is active."""

    def emit(self, record: logging.LogRecord) -> None:
        iid = _current_issue.get()
        if iid is None:
            return
        if not _should_keep(record):
            return
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": msg[:2000],
        }
        with _LOCK:
            buf = _BUFFERS.get(iid)
            if buf is None:
                buf = deque(maxlen=_MAX_ENTRIES)
                _BUFFERS[iid] = buf
            buf.append(entry)
            _LAST_WRITE[iid] = time.monotonic()


def set_current_issue(issue_id: Optional[str]) -> None:
    _current_issue.set(issue_id)


def start_buffer(issue_id: str) -> None:
    with _LOCK:
        if issue_id not in _BUFFERS:
            _BUFFERS[issue_id] = deque(maxlen=_MAX_ENTRIES)
        _LAST_WRITE[issue_id] = time.monotonic()


def tail(issue_id: str, since: Optional[str] = None) -> list[dict]:
    """Return entries newer than `since` (ISO timestamp, exclusive),
    or all entries if `since` is None. Also runs the lazy TTL sweep."""
    _evict_stale()
    with _LOCK:
        buf = _BUFFERS.get(issue_id)
        if buf is None:
            return []
        entries = list(buf)
    if since:
        entries = [e for e in entries if e["ts"] > since]
    return entries


def _evict_stale() -> None:
    now = time.monotonic()
    with _LOCK:
        for iid in list(_BUFFERS.keys()):
            if now - _LAST_WRITE.get(iid, 0) > _BUFFER_TTL_SECONDS:
                _BUFFERS.pop(iid, None)
                _LAST_WRITE.pop(iid, None)


def flush_to_db(issue_id: str) -> int:
    """Persist the in-memory buffer for this issue to the issue_logs
    table. Called from runner.run_issue()'s finally block so logs
    survive the backend reloads + buffer TTL that wipe the in-memory
    copy. Safe to call on an empty buffer (no-op). Returns the number
    of rows inserted."""
    import uuid as _uuid
    from datetime import datetime as _dt
    from sqlmodel import Session as _Session
    from app.db import engine as _engine
    from app.models import IssueLog

    with _LOCK:
        entries = list(_BUFFERS.get(issue_id, ()))
    if not entries:
        return 0

    try:
        iid = _uuid.UUID(issue_id)
    except ValueError:
        return 0

    rows: list[IssueLog] = []
    for e in entries:
        try:
            ts = _dt.fromisoformat(e["ts"])
        except Exception:
            ts = _dt.utcnow()
        rows.append(
            IssueLog(
                issue_id=iid,
                ts=ts,
                level=(e.get("level") or "INFO")[:16],
                logger_name=(e.get("logger") or "")[:128],
                msg=(e.get("msg") or "")[:4000],
            )
        )

    try:
        with _Session(_engine) as s:
            s.add_all(rows)
            s.commit()
    except Exception:
        import logging as _log

        _log.getLogger(__name__).exception(
            "flush_to_db failed for issue %s",
            issue_id,
        )
        return 0
    return len(rows)


def load_from_db(issue_id: str, since: Optional[str] = None) -> list[dict]:
    """Read the persisted log tail for an issue. Used as fallback when
    the in-memory buffer is empty (run finished long ago, backend
    reloaded, etc.). Returns entries shaped like the in-memory ones so
    the API can return either transparently."""
    import uuid as _uuid
    from datetime import datetime as _dt
    from sqlmodel import Session as _Session, select as _sel
    from app.db import engine as _engine
    from app.models import IssueLog

    try:
        iid = _uuid.UUID(issue_id)
    except ValueError:
        return []

    since_dt: Optional[_dt] = None
    if since:
        try:
            since_dt = _dt.fromisoformat(since)
        except Exception:
            since_dt = None

    try:
        with _Session(_engine) as s:
            q = _sel(IssueLog).where(IssueLog.issue_id == iid)
            if since_dt is not None:
                q = q.where(IssueLog.ts > since_dt)
            q = q.order_by(IssueLog.ts)
            rows = s.exec(q).all()
    except Exception:
        import logging as _log

        _log.getLogger(__name__).exception(
            "load_from_db failed for issue %s",
            issue_id,
        )
        return []

    out: list[dict] = []
    for r in rows:
        ts = r.ts.isoformat(timespec="milliseconds") if r.ts else ""
        out.append(
            {
                "ts": ts,
                "level": r.level,
                "logger": r.logger_name,
                "msg": r.msg,
            }
        )
    return out


def install_root_handler() -> None:
    """Attach the handler to the root logger once at app startup. Safe
    to call multiple times; idempotent via type check."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, IssueLogHandler):
            return
    handler = IssueLogHandler()
    handler.setLevel(logging.INFO)
    root.addHandler(handler)
    root_level = root.level or logging.WARNING
    if root_level > logging.INFO:
        root.setLevel(logging.INFO)
