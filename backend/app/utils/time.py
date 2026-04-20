from datetime import datetime, timezone


def now_utc() -> datetime:
    """Naive UTC datetime, for compatibility with the `timestamp without
    time zone` columns our models use. Replaces the deprecated
    datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
