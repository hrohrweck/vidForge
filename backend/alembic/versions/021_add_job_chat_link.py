"""add_job_chat_link

Revision ID: 021_add_job_chat_link
Revises: 020_add_message_job_id
Create Date: 2026-05-30 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "021_add_job_chat_link"
down_revision: Union[str, None] = "020_add_message_job_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("chat_conversation_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("chat_message_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_jobs_chat_conversation_id", "jobs", ["chat_conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_chat_conversation_id", table_name="jobs")
    op.drop_column("jobs", "chat_message_id")
    op.drop_column("jobs", "chat_conversation_id")
