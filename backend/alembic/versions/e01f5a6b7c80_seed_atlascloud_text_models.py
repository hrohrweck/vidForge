"""seed_atlascloud_text_models

Revision ID: e01f5a6b7c80
Revises: d01e4f5b6c70
Create Date: 2026-05-28 20:45:00.000000
"""

from alembic import op
from sqlalchemy import text
from uuid import uuid4

revision: str = "e01f5a6b7c80"
down_revision: str = "d01e4f5b6c70"
branch_labels = None
depends_on = None

ATLASCLOUD_TEXT_MODELS = [
    ("glm-5.1", "GLM 5.1"),
    ("glm-5.1-t", "GLM 5.1 Turbo"),
    ("deepseek-v3", "DeepSeek V3"),
    ("deepseek-r1", "DeepSeek R1"),
    ("qwen-max", "Qwen Max"),
    ("qwen-plus", "Qwen Plus"),
    ("gpt-4o", "GPT-4o"),
    ("claude-3.5-sonnet", "Claude 3.5 Sonnet"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("llama-4-maverick", "Llama 4 Maverick"),
]


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'atlascloud' AND is_active = true LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        return
    pid = str(row[0])

    for model_id, display_name in ATLASCLOUD_TEXT_MODELS:
        check = conn.execute(
            text("SELECT 1 FROM model_configs WHERE model_id = :mid AND provider_id = :pid"),
            {"mid": model_id, "pid": pid},
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
                "pid": pid,
                "mid": model_id,
                "pmid": model_id,
                "name": display_name,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'atlascloud' AND is_active = true LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        return
    pid = str(row[0])

    for model_id, _ in ATLASCLOUD_TEXT_MODELS:
        conn.execute(
            text("DELETE FROM model_configs WHERE model_id = :mid AND provider_id = :pid"),
            {"mid": model_id, "pid": pid},
        )
