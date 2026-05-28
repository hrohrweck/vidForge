"""fix_model_configs_column_types

Revision ID: d01e4f5b6c70
Revises: c01e3f4a5b60
Create Date: 2026-05-28 20:10:00.000000
"""

from alembic import op
from sqlalchemy import text

revision: str = "d01e4f5b6c70"
down_revision: str = "c01e3f4a5b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN modality DROP DEFAULT"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN prompt_format DROP DEFAULT"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN endpoint_type DROP DEFAULT"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN modality TYPE VARCHAR(20)"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN prompt_format TYPE VARCHAR(10)"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN endpoint_type TYPE VARCHAR(50)"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN modality SET DEFAULT 'image'"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN prompt_format SET DEFAULT 'string'"))
    conn.execute(text("ALTER TABLE model_configs ALTER COLUMN endpoint_type SET DEFAULT 'comfyui_workflow'"))
    conn.execute(text("DROP TYPE IF EXISTS model_configs_modality_enum CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS model_configs_prompt_format_enum CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS model_configs_endpoint_type_enum CASCADE"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "CREATE TYPE model_configs_modality_enum AS ENUM ('text', 'image', 'video')"
    ))
    conn.execute(text(
        "CREATE TYPE model_configs_prompt_format_enum AS ENUM ('string', 'array')"
    ))
    conn.execute(text(
        "CREATE TYPE model_configs_endpoint_type_enum AS ENUM "
        "('generateImage', 'generateVideo', 'chat_completions', 'video_endpoint', 'comfyui_workflow')"
    ))
    conn.execute(text(
        "ALTER TABLE model_configs ALTER COLUMN modality TYPE model_configs_modality_enum USING modality::model_configs_modality_enum"
    ))
    conn.execute(text(
        "ALTER TABLE model_configs ALTER COLUMN prompt_format TYPE model_configs_prompt_format_enum USING prompt_format::model_configs_prompt_format_enum"
    ))
    conn.execute(text(
        "ALTER TABLE model_configs ALTER COLUMN endpoint_type TYPE model_configs_endpoint_type_enum USING endpoint_type::model_configs_endpoint_type_enum"
    ))
