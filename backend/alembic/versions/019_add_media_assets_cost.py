"""add_cost_column_to_media_assets

Revision ID: 019_add_media_assets_cost
Revises: 423be74a99d5
Create Date: 2026-05-28 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019_add_media_assets_cost"
down_revision: Union[str, None] = "423be74a99d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("cost", sa.Numeric(10, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media_assets", "cost")
