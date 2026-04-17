"""Add scene media fields to video_scenes and jobs tables"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_scenes",
        sa.Column("image_provider_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "video_scenes",
        sa.Column("video_provider_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "video_scenes",
        sa.Column("image_prompt_enhanced", sa.Text, nullable=True),
    )
    op.add_column(
        "video_scenes",
        sa.Column("duration", sa.Float(), nullable=True),
    )
    op.add_column(
        "video_scenes",
        sa.Column("model_used", sa.String(100), nullable=True),
    )
    op.add_column(
        "video_scenes",
        sa.Column("seed", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "video_scenes",
        sa.Column("error_message", sa.Text, nullable=True),
    )

    op.add_column(
        "jobs",
        sa.Column("image_provider_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("video_provider_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("export_options", sa.JSONB, nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("workflow_type", sa.String(50), nullable=True),
    )

    op.create_foreign_key(
        "fk_scene_image_provider",
        "video_scenes", "providers",
        ["image_provider_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_scene_video_provider",
        "video_scenes", "providers",
        ["video_provider_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_job_image_provider",
        "jobs", "providers",
        ["image_provider_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_job_video_provider",
        "jobs", "providers",
        ["video_provider_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_job_video_provider", "jobs", type_="foreignkey")
    op.drop_constraint("fk_job_image_provider", "jobs", type_="foreignkey")
    op.drop_constraint("fk_scene_video_provider", "video_scenes", type_="foreignkey")
    op.drop_constraint("fk_scene_image_provider", "video_scenes", type_="foreignkey")

    op.drop_column("jobs", "workflow_type")
    op.drop_column("jobs", "export_options")
    op.drop_column("jobs", "video_provider_id")
    op.drop_column("jobs", "image_provider_id")
    op.drop_column("video_scenes", "error_message")
    op.drop_column("video_scenes", "seed")
    op.drop_column("video_scenes", "model_used")
    op.drop_column("video_scenes", "duration")
    op.drop_column("video_scenes", "image_prompt_enhanced")
    op.drop_column("video_scenes", "video_provider_id")
    op.drop_column("video_scenes", "image_provider_id")
