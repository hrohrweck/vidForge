"""Add model_configs table

Revision ID: 018
Revises: 017
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("provider_model_id", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column(
            "modality",
            sa.Enum(
                "text", "image", "video",
                name="model_configs_modality_enum", create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "prompt_format",
            sa.Enum(
                "string", "array",
                name="model_configs_prompt_format_enum", create_type=True,
            ),
            nullable=False,
            server_default="string",
        ),
        sa.Column(
            "endpoint_type",
            sa.Enum(
                "generateImage", "generateVideo", "chat_completions",
                "video_endpoint", "comfyui_workflow",
                name="model_configs_endpoint_type_enum", create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("parameter_map", JSONB, nullable=True),
        sa.Column("extra_params", JSONB, nullable=True),
        sa.Column("capabilities", JSONB, nullable=True),
        sa.Column("constraints", JSONB, nullable=True),
        sa.Column("cost_config", JSONB, nullable=True),
        sa.Column("comfyui_workflow", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_deprecated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("provider_id", "model_id", name="uq_model_configs_provider_model"),
    )
    op.create_index(
        "ix_model_configs_modality_active",
        "model_configs",
        ["modality", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_configs_modality_active", "model_configs")
    op.drop_table("model_configs")
    sa.Enum(name="model_configs_modality_enum").drop(op.get_bind())
    sa.Enum(name="model_configs_prompt_format_enum").drop(op.get_bind())
    sa.Enum(name="model_configs_endpoint_type_enum").drop(op.get_bind())
