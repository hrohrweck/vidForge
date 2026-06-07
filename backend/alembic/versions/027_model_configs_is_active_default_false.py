"""model_configs is_active default false

Revision ID: 027
Revises: 026
Create Date: 2026-06-07 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change server_default on is_active from 'true' to 'false'
    # so newly created model configs are disabled by default
    op.alter_column(
        "model_configs",
        "is_active",
        server_default=sa.text("'false'"),
        existing_server_default=sa.text("'true'"),
        existing_type=sa.Boolean,
        existing_nullable=False,
    )


def downgrade() -> None:
    # Restore original server_default
    op.alter_column(
        "model_configs",
        "is_active",
        server_default=sa.text("'true'"),
        existing_server_default=sa.text("'false'"),
        existing_type=sa.Boolean,
        existing_nullable=False,
    )
