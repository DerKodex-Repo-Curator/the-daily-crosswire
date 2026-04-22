"""newsletter_emails on configs + ingestion source tracking on news_items

Revision ID: d8a91c4e2b01
Revises: c5e7f1a9b3d2
Create Date: 2026-04-22 20:00:00.000000

Adds:
- newspaper_configs.newsletter_emails: list of recipient emails that
  receive a PDF of every successful issue via the notify node.
- news_items.ingested_via / source_feed_url / source_query: captures how
  each item was discovered so the Drops tab can show 'via RSS: <url>'
  or 'via SearXNG: <query>'. Legacy rows stay null; the UI omits the
  source line when the fields are missing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8a91c4e2b01"
down_revision: Union[str, None] = "c5e7f1a9b3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "newspaper_configs",
        sa.Column(
            "newsletter_emails",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "news_items",
        sa.Column("ingested_via", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "news_items",
        sa.Column("source_feed_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "news_items",
        sa.Column("source_query", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("news_items", "source_query")
    op.drop_column("news_items", "source_feed_url")
    op.drop_column("news_items", "ingested_via")
    op.drop_column("newspaper_configs", "newsletter_emails")
