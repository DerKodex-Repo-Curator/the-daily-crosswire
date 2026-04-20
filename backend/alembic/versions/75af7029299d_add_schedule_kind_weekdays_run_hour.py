"""add schedule kind, weekdays, run_hour

Revision ID: 75af7029299d
Revises: 0291ba4d70fe
Create Date: 2026-04-17 23:55:29.386664

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

revision: str = '75af7029299d'
down_revision: Union[str, None] = '0291ba4d70fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "newspaper_configs",
        sa.Column(
            "schedule_kind",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="interval",
        ),
    )
    op.add_column(
        "newspaper_configs",
        sa.Column("weekdays", postgresql.ARRAY(sa.Integer()), nullable=True),
    )
    op.add_column(
        "newspaper_configs",
        sa.Column(
            "run_hour", sa.Integer(), nullable=False, server_default="6"
        ),
    )
    op.alter_column(
        "newspaper_configs",
        "frequency_days",
        existing_type=sa.INTEGER(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "newspaper_configs",
        "frequency_days",
        existing_type=sa.INTEGER(),
        nullable=False,
    )
    op.drop_column("newspaper_configs", "run_hour")
    op.drop_column("newspaper_configs", "weekdays")
    op.drop_column("newspaper_configs", "schedule_kind")
