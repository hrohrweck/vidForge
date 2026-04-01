"""Provider support - workers, providers, cost tracking

Revision ID: 004
Revises: 003
Create Date: 2026-03-24

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("daily_budget_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("current_daily_spend", sa.Numeric(10, 2), server_default="0"),
        sa.Column("spend_reset_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("priority", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_providers_type", "providers", ["provider_type"])
    op.create_index("ix_providers_active", "providers", ["is_active"])

    op.create_table(
        "workers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), default="offline"),
        sa.Column("capabilities", JSONB, server_default="{}"),
        sa.Column("last_heartbeat", sa.DateTime, nullable=True),
        sa.Column("current_job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_workers_status", "workers", ["status"])
    op.create_index("ix_workers_provider", "workers", ["provider_id"])

    op.create_table(
        "cost_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", UUID(as_uuid=True), sa.ForeignKey("providers.id")),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id")),
        sa.Column("amount", sa.Numeric(10, 4), nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("gpu_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_cost_log_provider_date", "cost_log", ["provider_id", "created_at"])

    op.add_column(
        "jobs",
        sa.Column("provider_id", UUID(as_uuid=True), sa.ForeignKey("providers.id"), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("worker_id", UUID(as_uuid=True), sa.ForeignKey("workers.id"), nullable=True),
    )
    op.add_column("jobs", sa.Column("provider_type", sa.String(50), nullable=True))
    op.add_column("jobs", sa.Column("estimated_cost", sa.Numeric(10, 4), nullable=True))
    op.add_column("jobs", sa.Column("actual_cost", sa.Numeric(10, 4), nullable=True))
    op.create_index("ix_jobs_provider", "jobs", ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_provider", "jobs")
    op.drop_column("jobs", "actual_cost")
    op.drop_column("jobs", "estimated_cost")
    op.drop_column("jobs", "provider_type")
    op.drop_column("jobs", "worker_id")
    op.drop_column("jobs", "provider_id")

    op.drop_index("ix_cost_log_provider_date", "cost_log")
    op.drop_table("cost_log")

    op.drop_index("ix_workers_provider", "workers")
    op.drop_index("ix_workers_status", "workers")
    op.drop_table("workers")

    op.drop_index("ix_providers_active", "providers")
    op.drop_index("ix_providers_type", "providers")
    op.drop_table("providers")
