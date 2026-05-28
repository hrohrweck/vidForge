"""seed_poe_text_models

Revision ID: a76d1ce5c510
Revises: 77ec40b8a68e
Create Date: 2026-05-28 19:30:00.000000
"""

from alembic import op
from sqlalchemy import text
from uuid import uuid4

revision: str = "a76d1ce5c510"
down_revision: str = "77ec40b8a68e"
branch_labels = None
depends_on = None

TEXT_MODELS = [
    ("GPT-4o", "GPT-4o"),
    ("Claude-3.5-Sonnet", "Claude-3.5-Sonnet"),
    ("Claude-3-Opus", "Claude-3-Opus"),
    ("Gemini-2.5-Pro", "Gemini-2.5-Pro"),
    ("Gemini-2.5-Flash", "Gemini-2.5-Flash"),
    ("Llama-4-Maverick", "Llama-4-Maverick"),
    ("Llama-4-Scout", "Llama-4-Scout"),
    ("Qwen-3.6", "Qwen 3.6"),
    ("Mistral-Large", "Mistral Large"),
    ("DeepSeek-V3", "DeepSeek V3"),
]


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'poe' LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        return
    poe_uuid = str(row[0])

    for model_id, display_name in TEXT_MODELS:
        check = conn.execute(
            text("SELECT 1 FROM model_configs WHERE model_id = :mid AND provider_id = :pid"),
            {"mid": model_id, "pid": poe_uuid},
        )
        if check.fetchone():
            continue

        conn.execute(
            text(
                "INSERT INTO model_configs (id, provider_id, model_id, provider_model_id, "
                "display_name, modality, prompt_format, endpoint_type, is_active, created_at, updated_at) "
                "VALUES (:id, :pid, :mid, :pmid, :name, 'text', 'string', 'chat_completions', "
                "true, NOW(), NOW())"
            ),
            {
                "id": str(uuid4()),
                "pid": poe_uuid,
                "mid": model_id,
                "pmid": model_id,
                "name": display_name,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'poe' LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        return
    poe_uuid = str(row[0])

    for model_id, _ in TEXT_MODELS:
        conn.execute(
            text("DELETE FROM model_configs WHERE model_id = :mid AND provider_id = :pid"),
            {"mid": model_id, "pid": poe_uuid},
        )
