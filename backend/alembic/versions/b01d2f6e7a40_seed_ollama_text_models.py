"""seed_ollama_text_models

Revision ID: b01d2f6e7a40
Revises: a76d1ce5c510
Create Date: 2026-05-28 19:40:00.000000
"""

from alembic import op
from sqlalchemy import text
from uuid import uuid4

revision: str = "b01d2f6e7a40"
down_revision: str = "a76d1ce5c510"
branch_labels = None
depends_on = None

OLLAMA_MODELS = [
    ("qwen3.6:35b", "Qwen 3.6 35B"),
    ("llama3.3", "Llama 3.3"),
    ("deepseek-r1:14b", "DeepSeek R1 14B"),
    ("mistral:7b", "Mistral 7B"),
    ("phi4:14b", "Phi-4 14B"),
    ("gemma3:12b", "Gemma 3 12B"),
    ("codellama:13b", "CodeLlama 13B"),
]


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'comfyui_direct' LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        return
    provider_uuid = str(row[0])

    for model_id, display_name in OLLAMA_MODELS:
        check = conn.execute(
            text("SELECT 1 FROM model_configs WHERE model_id = :mid AND provider_id = :pid"),
            {"mid": model_id, "pid": provider_uuid},
        )
        if check.fetchone():
            continue

        conn.execute(
            text(
                "INSERT INTO model_configs (id, provider_id, model_id, provider_model_id, "
                "display_name, modality, prompt_format, endpoint_type, is_active, created_at, updated_at) "
                "VALUES (:id, :pid, :mid, :pmid, :name, 'text', 'string', 'comfyui_workflow', "
                "true, NOW(), NOW())"
            ),
            {
                "id": str(uuid4()),
                "pid": provider_uuid,
                "mid": model_id,
                "pmid": model_id,
                "name": display_name,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'comfyui_direct' LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        return
    provider_uuid = str(row[0])

    for model_id, _ in OLLAMA_MODELS:
        conn.execute(
            text("DELETE FROM model_configs WHERE model_id = :mid AND provider_id = :pid"),
            {"mid": model_id, "pid": provider_uuid},
        )
