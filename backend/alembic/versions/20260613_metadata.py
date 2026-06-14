"""add conversation metadata

Revision ID: 20260613_metadata
Revises: a8c8f2104949
Create Date: 2026-06-13 20:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260613_metadata"
down_revision: Union[str, None] = "a8c8f2104949"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation",
        sa.Column("metadata", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation", "metadata")
