"""add_scene_warnings

Revision ID: 024_add_scene_warnings
Revises: 023_normalize_user_settings
Create Date: 2026-06-06 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op


revision: str = "024_add_scene_warnings"
down_revision: Union[str, None] = "023_normalize_user_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_scenes",
        sa.Column("warnings", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("video_scenes", "warnings")
