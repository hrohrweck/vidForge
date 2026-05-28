"""fix_ollama_model_provider

Revision ID: c01e3f4a5b60
Revises: 178bb857d97b
Create Date: 2026-05-28 20:00:00.000000
"""

from alembic import op
from sqlalchemy import text

revision: str = "c01e3f4a5b60"
down_revision: str = "178bb857d97b"
branch_labels = None
depends_on = None

OLLAMA_MODELS = [
    "codellama:13b", "deepseek-r1:14b", "gemma3:12b",
    "mistral:7b", "phi4:14b", "qwen3.6:35b", "llama3.3",
]


def upgrade() -> None:
    conn = op.get_bind()
    ollama = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'ollama'")
    ).fetchone()
    comfyui = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'comfyui_direct'")
    ).fetchone()
    if not ollama or not comfyui:
        return

    moved = 0
    inserted = 0
    for mid in OLLAMA_MODELS:
        result = conn.execute(
            text("SELECT id FROM model_configs WHERE model_id = :mid AND provider_id = :pid"),
            {"mid": mid, "pid": str(comfyui[0])},
        )
        row = result.fetchone()
        if row:
            conn.execute(
                text("UPDATE model_configs SET provider_id = :oid WHERE id = :id"),
                {"oid": str(ollama[0]), "id": str(row[0])},
            )
            moved += 1
        else:
            # Not under comfyui — check if exists under ollama
            check = conn.execute(
                text("SELECT 1 FROM model_configs WHERE model_id = :mid AND provider_id = :oid"),
                {"mid": mid, "oid": str(ollama[0])},
            )
            if not check.fetchone():
                conn.execute(
                    text(
                        "INSERT INTO model_configs (id, provider_id, model_id, provider_model_id, "
                        "display_name, modality, prompt_format, endpoint_type, is_active, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :oid, :mid, :mid, :name, 'text', 'string', "
                        "'chat_completions', true, NOW(), NOW())"
                    ),
                    {"oid": str(ollama[0]), "mid": mid, "name": mid.replace(":latest", "")},
                )
                inserted += 1


def downgrade() -> None:
    conn = op.get_bind()
    ollama = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'ollama'")
    ).fetchone()
    comfyui = conn.execute(
        text("SELECT id FROM providers WHERE provider_type = 'comfyui_direct'")
    ).fetchone()
    if not ollama or not comfyui:
        return

    conn.execute(
        text("UPDATE model_configs SET provider_id = :cid WHERE provider_id = :oid AND model_id = ANY(:models)"),
        {"cid": str(comfyui[0]), "oid": str(ollama[0]), "models": OLLAMA_MODELS},
    )
