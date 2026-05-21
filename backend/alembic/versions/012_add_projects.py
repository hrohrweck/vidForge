"""Add projects table and link jobs/assets to projects

Revision ID: 012
Revises: 011
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "012"
down_revision: Union[str, None] = "011"


def upgrade() -> None:
    # Create projects table
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # Add project_id to jobs
    op.add_column(
        "jobs",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])

    # Add project_id to media_assets
    op.add_column(
        "media_assets",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_media_assets_project_id", "media_assets", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_media_assets_project_id", "media_assets")
    op.drop_column("media_assets", "project_id")
    op.drop_index("ix_jobs_project_id", "jobs")
    op.drop_column("jobs", "project_id")
    op.drop_index("ix_projects_user_id", "projects")
    op.drop_table("projects")
