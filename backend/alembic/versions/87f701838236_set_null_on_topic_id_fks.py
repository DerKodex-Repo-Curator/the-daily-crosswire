"""set null on topic_id FKs

Revision ID: 87f701838236
Revises: b543abf24789
Create Date: 2026-04-18 06:33:37.122309

Deleting a config cascades to topics (via ORM), but news_items.topic_id and
story_log.topic_id have RESTRICT semantics by default, which blocks topic
deletion whenever any news_item has been ingested. Change both FKs to
ON DELETE SET NULL so news_items/story_log rows survive config deletion
(useful as historical records) while topics go away cleanly.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '87f701838236'
down_revision: Union[str, None] = 'b543abf24789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("news_items_topic_id_fkey", "news_items", type_="foreignkey")
    op.create_foreign_key(
        "news_items_topic_id_fkey",
        "news_items",
        "topics",
        ["topic_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("story_log_topic_id_fkey", "story_log", type_="foreignkey")
    op.create_foreign_key(
        "story_log_topic_id_fkey",
        "story_log",
        "topics",
        ["topic_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("news_items_topic_id_fkey", "news_items", type_="foreignkey")
    op.create_foreign_key(
        "news_items_topic_id_fkey",
        "news_items",
        "topics",
        ["topic_id"],
        ["id"],
    )

    op.drop_constraint("story_log_topic_id_fkey", "story_log", type_="foreignkey")
    op.create_foreign_key(
        "story_log_topic_id_fkey",
        "story_log",
        "topics",
        ["topic_id"],
        ["id"],
    )
