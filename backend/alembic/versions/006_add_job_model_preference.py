"""Add model_preference column to jobs table"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("model_preference", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "model_preference")
