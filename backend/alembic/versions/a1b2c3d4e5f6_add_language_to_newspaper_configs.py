"""add language column to newspaper_configs

Revision ID: a1b2c3d4e5f6
Revises: 87f701838236
Create Date: 2026-04-20 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "87f701838236"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "newspaper_configs",
        sa.Column(
            "language",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="en",
        ),
    )


def downgrade() -> None:
    op.drop_column("newspaper_configs", "language")
