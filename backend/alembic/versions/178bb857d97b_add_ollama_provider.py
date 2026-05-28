"""add_ollama_provider

Revision ID: 178bb857d97b
Revises: b01d2f6e7a40
Create Date: 2026-05-28 19:47:18.793715

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text
from uuid import uuid4

# revision identifiers, used by Alembic.
revision: str = '178bb857d97b'
down_revision: Union[str, None] = 'b01d2f6e7a40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(text("SELECT 1 FROM providers WHERE provider_type = 'ollama'"))
    if not result.fetchone():
        conn.execute(
            text(
                "INSERT INTO providers (id, name, provider_type, config, is_active, "
                "daily_budget_limit, current_daily_spend, spend_reset_at, priority, created_at, updated_at) "
                "VALUES (:id, 'Ollama (Local)', 'ollama', :config, true, "
                "NULL, 0, NOW(), 0, NOW(), NOW())"
            ),
            {"id": str(uuid4()), "config": '{"base_url": "http://ollama:11434"}'},
        )

    conn.execute(
        text(
            "DELETE FROM model_configs WHERE model_id IN ('qwen3.6:35b', 'llama3.3') "
            "AND endpoint_type = 'comfyui_workflow'"
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM providers WHERE provider_type = 'ollama'"))
