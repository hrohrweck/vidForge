"""add_job_id_to_message

Revision ID: 020_add_message_job_id
Revises: 019_add_media_assets_cost
Create Date: 2026-05-30 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "020_add_message_job_id"
down_revision: Union[str, None] = "019_add_media_assets_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "message",
        sa.Column("job_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_message_job_id", "message", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_message_job_id", table_name="message")
    op.drop_column("message", "job_id")
