import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import Issue, NewsItem, StoryLog
from app.utils.time import now_utc

logger = logging.getLogger(__name__)


Decision = Literal["kept", "dropped_url", "dropped_title", "dropped_similarity"]


@dataclass
class DedupDecision:
    candidate_id: uuid.UUID
    candidate_url: str
    candidate_title: str
    decision: Decision
    match_info: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["candidate_id"] = str(self.candidate_id)
        return d


def dedup_window_days(frequency_days: Optional[int]) -> int:
    """Lookback window for dedup. Longer than the generation cadence so a
    weekly paper doesn't re-run the same story next week."""
    base = frequency_days or 1
    return max(base * 4, 14)


def filter_fresh(
    session: Session,
    candidates: list[NewsItem],
    window_days: int,
    sim_threshold: Optional[float] = None,
) -> tuple[list[NewsItem], list[DedupDecision]]:
    """Drop candidates that match any story_log entry from issues in the
    recent window by URL, normalized title, or semantic similarity.

    Rules applied in order (first match wins):
      1. Exact URL match against NewsItems already referenced by recent story_log.
      2. Exact normalized_title match (case/punctuation-insensitive).
      3. Cosine similarity > sim_threshold against recent rendered_title_embedding
         (only applied when the candidate has an embedding).
    """
    if not candidates:
        return [], []

    threshold = sim_threshold if sim_threshold is not None else settings.dedup_sim_threshold
    max_distance = 1.0 - threshold
    window_start = (now_utc() - timedelta(days=window_days)).date()

    existing_rows = session.exec(
        select(NewsItem.url, NewsItem.normalized_title)
        .join(StoryLog, StoryLog.news_item_id == NewsItem.id)
        .join(Issue, Issue.id == StoryLog.issue_id)
        .where(Issue.issue_date >= window_start)
    ).all()

    existing_urls = {row[0] for row in existing_rows}
    existing_titles = {row[1] for row in existing_rows}

    kept: list[NewsItem] = []
    decisions: list[DedupDecision] = []

    for c in candidates:
        if c.url in existing_urls:
            decisions.append(DedupDecision(c.id, c.url, c.title or "", "dropped_url"))
            continue

        if c.normalized_title in existing_titles:
            decisions.append(DedupDecision(c.id, c.url, c.title or "", "dropped_title"))
            continue

        if c.embedding is not None:
            distance_col = StoryLog.rendered_title_embedding.cosine_distance(c.embedding).label(
                "distance"
            )
            row = session.exec(
                select(
                    StoryLog.id,
                    StoryLog.rendered_title,
                    distance_col,
                )
                .join(Issue, Issue.id == StoryLog.issue_id)
                .where(Issue.issue_date >= window_start)
                .where(StoryLog.rendered_title_embedding.is_not(None))
                .order_by(distance_col)
                .limit(1)
            ).first()

            if row is not None:
                sl_id, matched_title, distance = row
                if distance is not None and distance < max_distance:
                    decisions.append(
                        DedupDecision(
                            c.id,
                            c.url,
                            c.title or "",
                            "dropped_similarity",
                            match_info={
                                "story_log_id": str(sl_id),
                                "matched_title": matched_title,
                                "similarity": round(1.0 - float(distance), 4),
                                "threshold": threshold,
                            },
                        )
                    )
                    continue

        kept.append(c)
        decisions.append(DedupDecision(c.id, c.url, c.title or "", "kept"))

    for d in decisions:
        if d.decision != "kept":
            logger.info(
                "dedup drop: %s  title=%r  match=%s",
                d.decision,
                d.candidate_title[:80],
                d.match_info,
            )

    return kept, decisions
