"""add_object_refs_tables

Revision ID: 028
Revises: 027
Create Date: 2026-06-07 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from alembic import op


revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "object_refs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("visual_properties", JSONB, nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "object_ref_images",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("object_ref_id", PG_UUID(as_uuid=True), sa.ForeignKey("object_refs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("is_primary", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "job_object_refs",
        sa.Column("job_id", PG_UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("object_ref_id", PG_UUID(as_uuid=True), sa.ForeignKey("object_refs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.Text, nullable=True),
        sa.Column("importance_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("job_id", "object_ref_id"),
    )


def downgrade() -> None:
    op.drop_table("job_object_refs")
    op.drop_table("object_ref_images")
    op.drop_table("object_refs")
