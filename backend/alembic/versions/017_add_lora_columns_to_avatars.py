"""Add lora columns to avatars (lora_model_path, lora_training_status)

Revision ID: 017
Revises: 016
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "avatars",
        sa.Column("lora_model_path", sa.String(500), nullable=True),
    )
    op.add_column(
        "avatars",
        sa.Column(
            "lora_training_status",
            sa.String(20),
            nullable=False,
            server_default="not_trained",
        ),
    )


def downgrade() -> None:
    op.drop_column("avatars", "lora_training_status")
    op.drop_column("avatars", "lora_model_path")
