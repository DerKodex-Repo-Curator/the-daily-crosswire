import logging
from typing import Any, Optional, TypedDict

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SearXNGError(Exception):
    pass


class SearchResult(TypedDict):
    url: Optional[str]
    title: Optional[str]
    content: Optional[str]
    engine: Optional[str]
    published_date: Optional[str]


_TIME_RANGES = {"day", "week", "month", "year"}


async def search(
    query: str,
    *,
    time_range: Optional[str] = None,
    engines: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    max_results: int = 20,
    timeout: float = 15.0,
) -> list[SearchResult]:
    """Query SearXNG and return a normalized list of results.

    `time_range` restricts recency ("day" | "week" | "month" | "year");
    map this from `frequency_days` when wiring the agent.
    """
    if time_range and time_range not in _TIME_RANGES:
        raise ValueError(f"time_range must be one of {sorted(_TIME_RANGES)}")

    params: dict[str, Any] = {"q": query, "format": "json"}
    if time_range:
        params["time_range"] = time_range
    if engines:
        params["engines"] = ",".join(engines)
    if categories:
        params["categories"] = ",".join(categories)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(f"{settings.searxng_url}/search", params=params)
        except httpx.HTTPError as exc:
            raise SearXNGError(f"searxng request failed: {exc}") from exc

    if resp.status_code != 200:
        raise SearXNGError(f"searxng returned HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise SearXNGError(f"invalid JSON from searxng: {exc}") from exc

    raw_results = data.get("results", []) or []
    normalized: list[SearchResult] = []
    for item in raw_results[:max_results]:
        normalized.append(
            {
                "url": item.get("url"),
                "title": item.get("title"),
                "content": item.get("content"),
                "engine": item.get("engine"),
                "published_date": item.get("publishedDate"),
            }
        )
    logger.info("searxng %r time_range=%s -> %d results", query, time_range, len(normalized))
    return normalized
