"""add_error_events

Revision ID: 024_add_error_events
Revises: 023_normalize_user_settings
Create Date: 2026-06-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "024_add_error_events"
down_revision: Union[str, None] = "023_normalize_user_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "error",
                "critical",
                "warning",
                "info",
                name="error_severity",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.Enum(
                "media_generation",
                "video_generation",
                "audio_generation",
                "llm",
                "storage",
                "upload",
                "system",
                name="error_origin",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("source_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_error_events_user_id", "error_events", ["user_id"])
    op.create_index("ix_error_events_severity", "error_events", ["severity"])
    op.create_index("ix_error_events_origin", "error_events", ["origin"])
    op.create_index(
        "ix_error_events_created_at",
        "error_events",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_error_events_user_created",
        "error_events",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_error_events_user_created", table_name="error_events")
    op.drop_index("ix_error_events_created_at", table_name="error_events")
    op.drop_index("ix_error_events_origin", table_name="error_events")
    op.drop_index("ix_error_events_severity", table_name="error_events")
    op.drop_index("ix_error_events_user_id", table_name="error_events")
    op.drop_table("error_events")
    op.execute("DROP TYPE IF EXISTS error_severity")
    op.execute("DROP TYPE IF EXISTS error_origin")
