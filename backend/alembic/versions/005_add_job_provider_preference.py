"""Store job provider preference for deferred starts"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("provider_preference", sa.String(50), nullable=False, server_default="auto"),
    )


def downgrade() -> None:
    op.drop_column("jobs", "provider_preference")
