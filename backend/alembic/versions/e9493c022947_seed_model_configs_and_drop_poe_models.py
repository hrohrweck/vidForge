"""seed_model_configs_and_drop_poe_models

Revision ID: e9493c022947
Revises: 018
Create Date: 2026-05-28 14:06:19.029443

Seeds model_configs from static data (model_config.py, model_registry.py,
VIDEO_WORKFLOW_MAP) and from the poe_models table, then drops poe_models.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "e9493c022947"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Static data copied from model_config.py AVAILABLE_IMAGE_MODELS
_IMAGE_MODELS = [
    {
        "model_id": "flux1-schnell",
        "display_name": "FLUX.1-schnell",
        "comfyui_workflow": "flux_image.json",
        "capabilities": ["text-to-image"],
    },
    {
        "model_id": "sdxl",
        "display_name": "Stable Diffusion XL",
        "comfyui_workflow": "sdxl_image.json",
        "capabilities": ["text-to-image"],
    },
]

_VIDEO_FAMILY_MODELS = [
    {
        "model_id": "wan2.2",
        "display_name": "WAN 2.2",
        "capabilities": ["text-to-video", "image-to-video", "scene-to-video"],
    },
    {
        "model_id": "ltx2.3",
        "display_name": "LTX 2.3",
        "capabilities": ["text-to-video", "image-to-video"],
    },
    {
        "model_id": "ltx2.3-fast",
        "display_name": "LTX 2.3 Fast",
        "capabilities": ["text-to-video"],
    },
]

# Copied from media_generator.py VIDEO_WORKFLOW_MAP
_VIDEO_WORKFLOW_MAP: dict[str, str] = {
    "wan2.2_t2v": "wan_t2v.json",
    "wan2.2_s2v": "wan_s2v.json",
    "wan2.2_i2v": "wan_i2v.json",
    "wan_t2v": "wan_t2v.json",
    "wan_s2v": "wan_s2v.json",
    "wan_i2v": "wan_i2v.json",
    "ltx2.3_t2v": "ltx_t2v.json",
    "ltx2.3_i2v": "ltx_i2v.json",
    "ltx_t2v": "ltx_t2v.json",
    "ltx_i2v": "ltx_i2v.json",
    "ltx_distilled": "ltx_distilled.json",
    "ltx2.3_distilled": "ltx_distilled.json",
}

# Copied from model_registry.py MODELS dict
_REGISTRY_MODELS: dict[str, dict] = {
    "wan2.2_t2v": {
        "display_name": "WAN 2.2",
        "capabilities": ["text-to-video"],
        "max_duration": 30,
        "max_resolution": "1920x1080",
    },
    "wan2.2_s2v": {
        "display_name": "WAN 2.2",
        "capabilities": ["text-to-video", "scene-to-video"],
        "max_duration": 30,
        "max_resolution": "1920x1080",
    },
    "wan2.2_i2v": {
        "display_name": "WAN 2.2",
        "capabilities": ["image-to-video"],
        "max_duration": 30,
        "max_resolution": "1920x1080",
    },
    "ltx2.3_t2v": {
        "display_name": "LTX 2.3",
        "capabilities": ["text-to-video", "audio-to-video"],
        "max_duration": 20,
        "max_resolution": "1920x1080",
    },
    "ltx2.3_distilled": {
        "display_name": "LTX 2.3 Fast",
        "capabilities": ["text-to-video", "audio-to-video"],
        "max_duration": 20,
        "max_resolution": "1920x1080",
    },
    "ltx2.3_i2v": {
        "display_name": "LTX 2.3",
        "capabilities": ["image-to-video", "audio-to-video"],
        "max_duration": 20,
        "max_resolution": "1920x1080",
    },
}

# Poe video API models (from poe.py _VIDEO_API_MODELS)
_POE_VIDEO_API_MODELS = {
    "veo-3.1", "veo-3.1-fast", "veo-3", "veo-2", "veo-2-video",
    "veo-v3.1", "veo-v3.1-fast", "veo-3-vfast", "veo-3-fast",
}


def _get_provider_uuids(conn) -> dict[str, str]:
    rows = conn.execute(
        sa.text("SELECT id, provider_type FROM providers")
    ).fetchall()
    return {row[1]: str(row[0]) for row in rows}


def _seed_image_models(conn, comfyui_uuid: str) -> None:
    for m in _IMAGE_MODELS:
        conn.execute(
            sa.text("""
                INSERT INTO model_configs (
                    id, provider_id, model_id, provider_model_id,
                    display_name, modality, prompt_format, endpoint_type,
                    comfyui_workflow, capabilities, is_active, is_deprecated
                ) VALUES (
                    gen_random_uuid(), :pid, :mid, :mid,
                    :display, 'image', 'string', 'comfyui_workflow',
                    :wf, :caps, true, false
                )
                ON CONFLICT (provider_id, model_id) DO NOTHING
            """),
            {
                "pid": comfyui_uuid,
                "mid": m["model_id"],
                "display": m["display_name"],
                "wf": m["comfyui_workflow"],
                "caps": json.dumps(m["capabilities"]),
            },
        )


def _seed_video_families(conn, comfyui_uuid: str) -> None:
    for m in _VIDEO_FAMILY_MODELS:
        conn.execute(
            sa.text("""
                INSERT INTO model_configs (
                    id, provider_id, model_id, provider_model_id,
                    display_name, modality, prompt_format, endpoint_type,
                    capabilities, is_active, is_deprecated
                ) VALUES (
                    gen_random_uuid(), :pid, :mid, :mid,
                    :display, 'video', 'string', 'comfyui_workflow',
                    :caps, true, false
                )
                ON CONFLICT (provider_id, model_id) DO NOTHING
            """),
            {
                "pid": comfyui_uuid,
                "mid": m["model_id"],
                "display": m["display_name"],
                "caps": json.dumps(m["capabilities"]),
            },
        )


def _seed_workflow_variants(conn, comfyui_uuid: str) -> None:
    for variant_id, wf_file in _VIDEO_WORKFLOW_MAP.items():
        reg = _REGISTRY_MODELS.get(variant_id)
        display = reg["display_name"] if reg else variant_id
        conn.execute(
            sa.text("""
                INSERT INTO model_configs (
                    id, provider_id, model_id, provider_model_id,
                    display_name, modality, prompt_format, endpoint_type,
                    comfyui_workflow, is_active, is_deprecated
                ) VALUES (
                    gen_random_uuid(), :pid, :mid, :mid,
                    :display, 'video', 'string', 'comfyui_workflow',
                    :wf, true, false
                )
                ON CONFLICT (provider_id, model_id) DO NOTHING
            """),
            {
                "pid": comfyui_uuid,
                "mid": variant_id,
                "display": display,
                "wf": wf_file,
            },
        )


def _update_from_registry(conn, comfyui_uuid: str) -> None:
    for model_id, reg in _REGISTRY_MODELS.items():
        constraints = {
            "max_duration": reg["max_duration"],
            "max_resolution": reg["max_resolution"],
        }
        conn.execute(
            sa.text("""
                UPDATE model_configs
                SET capabilities  = :caps,
                    constraints   = :constraints,
                    display_name  = :display
                WHERE provider_id = :pid
                  AND model_id    = :mid
            """),
            {
                "caps": json.dumps(reg["capabilities"]),
                "constraints": json.dumps(constraints),
                "display": reg["display_name"],
                "pid": comfyui_uuid,
                "mid": model_id,
            },
        )


def _seed_from_poe_models(conn, poe_uuid: str) -> None:
    video_ids = ", ".join(f"'{m}'" for m in _POE_VIDEO_API_MODELS)
    conn.execute(
        sa.text(f"""
            INSERT INTO model_configs (
                id, provider_id, model_id, provider_model_id,
                display_name, modality, prompt_format, endpoint_type,
                capabilities, is_active, is_deprecated
            )
            SELECT
                gen_random_uuid(),
                pm.provider_id,
                pm.model_id,
                pm.model_id,
                pm.name,
                pm.modality::model_configs_modality_enum,
                'string'::model_configs_prompt_format_enum,
                CASE
                    WHEN LOWER(pm.model_id) IN ({video_ids})
                    THEN 'video_endpoint'::model_configs_endpoint_type_enum
                    WHEN pm.modality = 'image'
                    THEN 'generateImage'::model_configs_endpoint_type_enum
                    WHEN pm.modality = 'video'
                    THEN 'generateVideo'::model_configs_endpoint_type_enum
                    ELSE 'chat_completions'::model_configs_endpoint_type_enum
                END,
                '[]'::jsonb,
                pm.is_active,
                false
            FROM poe_models pm
            ON CONFLICT (provider_id, model_id) DO NOTHING
        """)
    )


def upgrade() -> None:
    conn = op.get_bind()
    providers = _get_provider_uuids(conn)
    comfyui_uuid = providers.get("comfyui_direct")
    poe_uuid = providers.get("poe")

    if comfyui_uuid:
        _seed_image_models(conn, comfyui_uuid)
        _seed_video_families(conn, comfyui_uuid)
        _seed_workflow_variants(conn, comfyui_uuid)
        _update_from_registry(conn, comfyui_uuid)

    if poe_uuid:
        _seed_from_poe_models(conn, poe_uuid)

    op.execute("DROP INDEX IF EXISTS ix_poe_models_provider_id")
    op.drop_table("poe_models")


def downgrade() -> None:
    op.create_table(
        "poe_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("modality", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_poe_models_provider_id", "poe_models", ["provider_id"])

    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM model_configs
            WHERE provider_id IN (
                SELECT id FROM providers
                WHERE provider_type IN ('comfyui_direct', 'poe')
            )
        """)
    )
