"""add issue_logs table for persisted per-run log tail

Revision ID: c5e7f1a9b3d2
Revises: a1b2c3d4e5f6
Create Date: 2026-04-20 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5e7f1a9b3d2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "issue_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "issue_id",
            sa.Uuid(),
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("logger_name", sa.String(length=128), nullable=False),
        sa.Column("msg", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_issue_logs_issue_id_ts",
        "issue_logs",
        ["issue_id", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_issue_logs_issue_id_ts", table_name="issue_logs")
    op.drop_table("issue_logs")
