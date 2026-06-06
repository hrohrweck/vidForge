"""merge_heads

Revision ID: f637742c0fd3
Revises: 022_sync_atlascloud_capabilities_from_poe, 025_add_media_events
Create Date: 2026-06-06 08:28:02.416667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f637742c0fd3'
down_revision: Union[str, None] = ('022_sync_atlascloud_capabilities_from_poe', '025_add_media_events')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
