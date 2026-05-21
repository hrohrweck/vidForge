"""Add media library tables

Revision ID: 011
Revises: 010
Create Date: 2026-05-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create media_folders table
    op.create_table(
        "media_folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("media_folders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_media_folders_user_parent", "media_folders", ["user_id", "parent_id"])
    op.create_index("ix_media_folders_user_id", "media_folders", ["user_id"])
    op.create_unique_constraint("uq_media_folders_user_parent_name", "media_folders", ["user_id", "parent_id", "name"])

    # Create media_assets table
    op.create_table(
        "media_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("media_folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("preview_path", sa.String(1024), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_media_assets_user_folder_created", "media_assets", ["user_id", "folder_id", sa.text("created_at DESC")])
    op.create_index("ix_media_assets_user_job", "media_assets", ["user_id", "source_job_id"])
    op.create_index("ix_media_assets_user_id", "media_assets", ["user_id"])

    # Create media_tags table
    op.create_table(
        "media_tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("color", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_media_tags_user_name", "media_tags", ["user_id", "name"])
    op.create_index("ix_media_tags_user_id", "media_tags", ["user_id"])

    # Create media_asset_tags junction table
    op.create_table(
        "media_asset_tags",
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("media_tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # Create media_asset_references table
    op.create_table(
        "media_asset_references",
        sa.Column("referrer_asset_id", UUID(as_uuid=True), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("referenced_asset_id", UUID(as_uuid=True), sa.ForeignKey("media_assets.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_media_asset_refs_referenced", "media_asset_references", ["referenced_asset_id"])


def downgrade() -> None:
    op.drop_table("media_asset_references")
    op.drop_table("media_asset_tags")
    op.drop_table("media_tags")
    op.drop_table("media_assets")
    op.drop_table("media_folders")
