"""Shared pytest fixtures.

Tests assume the stack is already running (`docker compose up -d`) and hit
localhost endpoints. Destructive fixtures (`clean_db`) are scoped to test
data only -- configs whose name starts with '__test' -- so they are safe
to run against a dev database that also has real configs.
"""

import os
import shutil

import httpx
import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Issue, NewsItem, NewspaperConfig, RSSFeed, StoryLog, Topic

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
TEST_CONFIG_PREFIX = "__test"


@pytest.fixture(scope="session")
def client():
    # Long default: a full agent run does RSS + (optional) SearXNG +
    # embedding batch + several LLM calls + render. Worst-case ~4 minutes.
    with httpx.Client(base_url=BASE_URL, timeout=600.0) as c:
        yield c


@pytest.fixture
def clean_db():
    """Wipe ONLY rows tied to test configs (name LIKE '__test%'). User's real
    configs/topics/news_items/issues are left alone. Also removes
    `issues/{slug}/` directories for wiped issues."""

    def _wipe():
        with Session(engine) as s:
            test_configs = s.exec(
                select(NewspaperConfig).where(NewspaperConfig.name.like(f"{TEST_CONFIG_PREFIX}%"))
            ).all()
            if not test_configs:
                return

            test_config_ids = [c.id for c in test_configs]
            test_topic_ids = [
                t.id
                for t in s.exec(select(Topic).where(Topic.config_id.in_(test_config_ids))).all()
            ]
            test_issue_slugs = [
                i.slug
                for i in s.exec(select(Issue).where(Issue.config_id.in_(test_config_ids))).all()
            ]
            # Capture the ingested news_items for these test topics BEFORE
            # deleting the config, so we can remove them after the cascade
            # has nulled their topic_id.
            test_news_item_ids = (
                [
                    n.id
                    for n in s.exec(
                        select(NewsItem).where(NewsItem.topic_id.in_(test_topic_ids))
                    ).all()
                ]
                if test_topic_ids
                else []
            )

            # Delete configs first. Cascades: topics (-> rss_feeds), issues
            # (-> story_log). news_items.topic_id is ON DELETE SET NULL, so
            # test news_items survive with topic_id=NULL.
            for c in test_configs:
                s.delete(c)
            s.commit()

            # Now remove those specific news_items so their URLs don't
            # collide with future runs.
            for nid in test_news_item_ids:
                item = s.get(NewsItem, nid)
                if item is not None:
                    s.delete(item)
            s.commit()

        # Filesystem cleanup: remove rendered output dirs for wiped test issues.
        for slug in test_issue_slugs:
            d = settings.issues_dir / slug
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        # Also remove any orphan test dirs from earlier runs that crashed before cleanup.
        if settings.issues_dir.is_dir():
            for child in settings.issues_dir.iterdir():
                if not child.is_dir():
                    continue
                if TEST_CONFIG_PREFIX in child.name:
                    shutil.rmtree(child, ignore_errors=True)

    _wipe()
    yield
    _wipe()
