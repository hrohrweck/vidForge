"""add job title

Revision ID: 013
Revises: 012
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("title", sa.String(255), nullable=True),
    )
    # Backfill: set a default title for existing jobs
    op.execute("UPDATE jobs SET title = 'Untitled Video' WHERE title IS NULL")
    # Now make it NOT NULL
    op.alter_column("jobs", "title", nullable=False)


def downgrade() -> None:
    op.drop_column("jobs", "title")
