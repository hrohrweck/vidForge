"""add_media_events

Revision ID: 025_add_media_events
Revises: 024_add_error_events
Create Date: 2026-06-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "025_add_media_events"
down_revision: Union[str, None] = "024_add_error_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), nullable=True),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_media_events_user_id", "media_events", ["user_id"])
    op.create_index("ix_media_events_event_type", "media_events", ["event_type"])
    op.create_index("ix_media_events_asset_id", "media_events", ["asset_id"])
    op.create_index("ix_media_events_seq", "media_events", ["seq"])
    op.create_index(
        "ix_media_events_user_seq",
        "media_events",
        ["user_id", "seq"],
    )
    op.create_index(
        "ix_media_events_user_created",
        "media_events",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_media_events_user_created", table_name="media_events")
    op.drop_index("ix_media_events_user_seq", table_name="media_events")
    op.drop_index("ix_media_events_seq", table_name="media_events")
    op.drop_index("ix_media_events_asset_id", table_name="media_events")
    op.drop_index("ix_media_events_event_type", table_name="media_events")
    op.drop_index("ix_media_events_user_id", table_name="media_events")
    op.drop_table("media_events")
