"""add drafts_json, rendered_body, max_stories_per_topic

Revision ID: b543abf24789
Revises: 6c90dd2ce7e1
Create Date: 2026-04-18 00:29:58.936816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b543abf24789'
down_revision: Union[str, None] = '6c90dd2ce7e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'issues',
        sa.Column('drafts_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'newspaper_configs',
        sa.Column('max_stories_per_topic', sa.Integer(), nullable=True),
    )
    op.add_column(
        'story_log',
        sa.Column('rendered_body', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('story_log', 'rendered_body')
    op.drop_column('newspaper_configs', 'max_stories_per_topic')
    op.drop_column('issues', 'drafts_json')
