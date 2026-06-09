"""add_is_chat_enabled_to_model_configs

Revision ID: 029
Revises: 028
Create Date: 2026-06-09 11:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '029'
down_revision: Union[str, None] = '028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_chat_enabled column to model_configs with default True
    op.add_column('model_configs', sa.Column('is_chat_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    # Create index for efficient filtering
    op.create_index('ix_model_configs_chat_enabled', 'model_configs', ['is_chat_enabled'], unique=False)


def downgrade() -> None:
    # Drop index and column
    op.drop_index('ix_model_configs_chat_enabled', table_name='model_configs')
    op.drop_column('model_configs', 'is_chat_enabled')
