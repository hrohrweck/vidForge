"""Add chatbot tables (conversation, message, mcp_server, chat_token_usage)

Revision ID: 015
Revises: 014
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # conversation table
    op.create_table(
        "conversation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_conversation_user_id", "conversation", ["user_id"])

    # message table
    op.create_table(
        "message",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tool_calls", JSONB, nullable=True),
        sa.Column("tool_call_id", sa.String(255), nullable=True),
        sa.Column("attachments", JSONB, nullable=True),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_message_conversation_id", "message", ["conversation_id"])

    # mcp_server table
    op.create_table(
        "mcp_server",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("auth_type", sa.String(20), nullable=False, server_default="'none'"),
        sa.Column("encrypted_credentials", sa.LargeBinary, nullable=True),
        sa.Column("enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # chat_token_usage table
    op.create_table(
        "chat_token_usage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column(
            "conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_token_usage_user_model_recorded", "chat_token_usage", ["user_id", "model_id", "recorded_at"])


def downgrade() -> None:
    op.drop_table("chat_token_usage")
    op.drop_table("mcp_server")
    op.drop_table("message")
    op.drop_table("conversation")