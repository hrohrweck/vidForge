"""Add avatar tables (avatars, avatar_images, job_avatars)

Revision ID: 016
Revises: 015
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "avatars",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("gender", sa.String(20), nullable=False),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column(
            "consistency_strategy",
            sa.Enum(
                "ip_adapter", "face_swap", "lora", "prompt_only",
                name="consistency_strategy_enum", create_type=True,
            ),
            nullable=False,
            server_default="ip_adapter",
        ),
        sa.Column("primary_image_id", UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_avatars_user_id", "avatars", ["user_id"])
    op.create_index("ix_avatars_deleted_at", "avatars", ["deleted_at"])

    # avatar_images table
    op.create_table(
        "avatar_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "avatar_id", UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_avatar_images_avatar_id", "avatar_images", ["avatar_id"])

    # Deferrable FK from avatars.primary_image_id → avatar_images.id
    # (added after avatar_images exists to avoid circular dependency)
    op.create_foreign_key(
        "fk_avatars_primary_image_id",
        "avatars", "avatar_images",
        ["primary_image_id"], ["id"],
        deferrable=True,
        initially="DEFERRED",
    )

    # job_avatars join table
    op.create_table(
        "job_avatars",
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("avatar_id", UUID(as_uuid=True), sa.ForeignKey("avatars.id"), primary_key=True),
        sa.Column("role", sa.Text, nullable=True),
        sa.Column("consistency_strategy_override", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Drop FK constraint before tables it references
    op.drop_constraint("fk_avatars_primary_image_id", "avatars", type_="foreignkey")
    op.drop_table("job_avatars")
    op.drop_table("avatar_images")
    op.drop_table("avatars")
    sa.Enum(
        "ip_adapter", "face_swap", "lora", "prompt_only",
        name="consistency_strategy_enum",
    ).drop(op.get_bind())
