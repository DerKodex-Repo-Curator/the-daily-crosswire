"""switch embedding dim to 768

Revision ID: 6c90dd2ce7e1
Revises: 75af7029299d
Create Date: 2026-04-18 00:08:25.393697

Swaps both vector columns from 1536 (text-embedding-3-small) to 768
(nomic-embed-text). Safe because no embeddings have been stored yet.
If you already have data, clear news_items.embedding and
story_log.rendered_title_embedding first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


revision: str = '6c90dd2ce7e1'
down_revision: Union[str, None] = '75af7029299d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_DIM = 768
OLD_DIM = 1536


def _swap_vector_column(table: str, column: str, index: str, dim: int) -> None:
    op.execute(f"DROP INDEX IF EXISTS {index}")
    op.drop_column(table, column)
    op.add_column(
        table,
        sa.Column(column, pgvector.sqlalchemy.Vector(dim), nullable=True),
    )
    op.execute(
        f"CREATE INDEX {index} ON {table} "
        f"USING ivfflat ({column} vector_cosine_ops) WITH (lists = 100)"
    )


def upgrade() -> None:
    _swap_vector_column("news_items", "embedding", "ix_news_items_embedding", NEW_DIM)
    _swap_vector_column(
        "story_log",
        "rendered_title_embedding",
        "ix_story_log_rendered_embedding",
        NEW_DIM,
    )


def downgrade() -> None:
    _swap_vector_column("news_items", "embedding", "ix_news_items_embedding", OLD_DIM)
    _swap_vector_column(
        "story_log",
        "rendered_title_embedding",
        "ix_story_log_rendered_embedding",
        OLD_DIM,
    )
