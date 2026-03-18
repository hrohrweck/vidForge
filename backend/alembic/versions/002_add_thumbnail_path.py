"""Add thumbnail_path to jobs

Revision ID: 002
Revises: 001
Create Date: 2024-01-02

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("thumbnail_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "thumbnail_path")
