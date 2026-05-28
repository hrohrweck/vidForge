"""seed_initial_model_pricing

Revision ID: 77ec40b8a68e
Revises: 019_add_media_assets_cost
Create Date: 2026-05-28 18:24:53.383292

Seed cost_config for existing model_configs rows from documented pricing:

Poe models → compute_points extracted from:
  docs/Provider/Poe/poe-image-video-model-parameters.md §8

AtlasCloud models → USD-per-generation/extracted from:
  docs/Provider/Atlascloud/atlascloud-image-video-model-parameters.md §6-§7

ComfyUI Direct models → cost=0 (local generation).
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "77ec40b8a68e"
down_revision: Union[str, None] = "019_add_media_assets_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── helpers ──────────────────────────────────────────────────────────

def _j(obj) -> str:
    """JSON-serialize a dict for use as a sa.text bound parameter."""
    return json.dumps(obj)


def _get_provider_id(conn, provider_type: str) -> str | None:
    row = conn.execute(
        sa.text("SELECT id FROM providers WHERE provider_type = :ptype"),
        {"ptype": provider_type},
    ).fetchone()
    return str(row[0]) if row else None


def _upsert_cost(
    conn,
    provider_id: str,
    cost_config: dict,
    *model_id_patterns: str,
) -> None:
    """UPDATE model_configs.cost_config for rows that match any LIKE pattern.

    Patterns are case-insensitive on model_id.
    Returns early if no models match (no-op for missing models).
    """
    clauses = " OR ".join(
        f"LOWER(model_id) LIKE LOWER(:p{i})" for i in range(len(model_id_patterns))
    )
    params = {f"p{i}": pat for i, pat in enumerate(model_id_patterns)}
    params["pid"] = provider_id
    params["cc"] = _j(cost_config)
    conn.execute(
        sa.text(f"""
            UPDATE model_configs
            SET cost_config = CAST(:cc AS jsonb)
            WHERE provider_id = CAST(:pid AS uuid)
              AND ({clauses})
        """),
        params,
    )


# ══════════════════════════════════════════════════════════════════════
# Poe model compute-point costs (from docs §8)
# ══════════════════════════════════════════════════════════════════════

_POE_PRICING: list[tuple[dict, list[str]]] = [
    # cost_config, [model_id LIKE patterns]
    ({"compute_points": 92000, "currency": "compute_points"},
     ["veo-3.1%", "veo-v3.1%", "veo-3%", "veo-2%", "veo%"]),
    ({"compute_points": 12670, "currency": "compute_points"},
     ["kling-pro%v1.5%", "kling-pro%"]),
    ({"compute_points": 30000, "currency": "compute_points"},
     ["kling-2.0-master%", "kling-2.0%"]),
    ({"compute_points": 5000, "currency": "compute_points"},
     ["pika-turbo%"]),
    ({"compute_points": 5834, "currency": "compute_points"},
     ["pika-v2.1%", "pika-v2.2%", "pika%"]),
    ({"compute_points": 7084, "currency": "compute_points"},
     ["pika%ingredients%"]),
    ({"compute_points": 11750, "currency": "compute_points"},
     ["ray-2%", "ray2%"]),
    ({"compute_points": 12000, "currency": "compute_points"},
     ["dream-machine%", "dream%machine%"]),
    ({"compute_points": 21334, "currency": "compute_points"},
     ["runway-gen-4-turbo%", "runway-gen-4%", "runway%"]),
    ({"compute_points": 14000, "currency": "compute_points"},
     ["hailuo-ai%", "hailuo%ai%"]),
    ({"compute_points": 14167, "currency": "compute_points"},
     ["hailuo-live%"]),
    # Sora-2: not directly listed in hard compute points; approximate 15000
    ({"compute_points": 15000, "currency": "compute_points"},
     ["sora-2%", "sora2%"]),
    # Grok-Imagine: not directly listed; approximate 12000
    ({"compute_points": 12000, "currency": "compute_points"},
     ["grok-imagine-video%", "grok%imagine%video%"]),
]


# ══════════════════════════════════════════════════════════════════════
# AtlasCloud model credits pricing (from markdown §6–§7)
# ══════════════════════════════════════════════════════════════════════

_ATLAS_PRICING: list[tuple[dict, list[str]]] = [
    # ── image models (§6) ──
    ({"credits_per_image": 0.003, "credits_per_second": 0, "currency": "credits"},
     ["bytedance/z-image-turbo%"]),
    ({"credits_per_image": 0.010, "credits_per_second": 0, "currency": "credits"},
     ["openai/gpt-image-2%"]),
    ({"credits_per_image": 0.030, "credits_per_second": 0, "currency": "credits"},
     ["wan-2.7%/text-to-image", "wan-2.7%/image-to-image"]),
    ({"credits_per_image": 0.075, "credits_per_second": 0, "currency": "credits"},
     ["wan-2.7-pro%", "qwen-image-2.0-pro%"]),
    ({"credits_per_image": 0.035, "credits_per_second": 0, "currency": "credits"},
     ["qwen-image-2.0%", "seedream-v5.0-lite%"]),
    ({"credits_per_image": 0.080, "credits_per_second": 0, "currency": "credits"},
     ["nano-banana-2%"]),
    ({"credits_per_image": 0.060, "credits_per_second": 0, "currency": "credits"},
     ["xai/grok-imagine-image-quality%"]),
    ({"credits_per_image": 0.000, "credits_per_second": 0, "currency": "credits"},
     ["baidu/ernie-image-turbo%"]),
    # ── video models (§7) ──
    ({"credits_per_image": 0, "credits_per_second": 0.112, "currency": "credits"},
     ["bytedance/seedance-2.0%/text-to-video", "bytedance/seedance-2.0%/image-to-video",
      "bytedance/seedance-2.0%/reference-to-video"]),
    ({"credits_per_image": 0, "credits_per_second": 0.09, "currency": "credits"},
     ["bytedance/seedance-2.0-fast%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.10, "currency": "credits"},
     ["wan-2.7%/text-to-video", "wan-2.7%/image-to-video", "wan-2.7%/reference-to-video",
      "wan-2.7%/video-edit"]),
    ({"credits_per_image": 0, "credits_per_second": 0.02, "currency": "credits"},
     ["wan-2.2-turbo%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.026, "currency": "credits"},
     ["wan-2.2-turbo%lora%", "wan-2.2-turbo-infinite%lora%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.20, "currency": "credits"},
     ["google/veo3.1%/text-to-video", "google/veo3.1%/image-to-video",
      "google/veo3.1%/reference-to-video"]),
    ({"credits_per_image": 0, "credits_per_second": 0.08, "currency": "credits"},
     ["google/veo3.1-fast%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.05, "currency": "credits"},
     ["google/veo3.1-lite%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.15, "currency": "credits"},
     ["google/gemini-omni-flash%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.14, "currency": "credits"},
     ["happyhorse-1.0%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.125, "currency": "credits"},
     ["vidu/q3-mix%"]),
    ({"credits_per_image": 0, "credits_per_second": 0.05, "currency": "credits"},
     ["vidu/q3%reference-to-video%"]),
]


# ══════════════════════════════════════════════════════════════════════
# ComfyUI Direct (free local generation)
# ══════════════════════════════════════════════════════════════════════

_COMFY_COST = {"cost": 0, "currency": "USD", "note": "local_generation"}


def upgrade() -> None:
    conn = op.get_bind()

    # ── Poe ────────────────────────────────────────────────────────
    poe_id = _get_provider_id(conn, "poe")
    if poe_id:
        for cost_config, patterns in _POE_PRICING:
            _upsert_cost(conn, poe_id, cost_config, *patterns)

    # ── AtlasCloud ─────────────────────────────────────────────────
    atlas_id = _get_provider_id(conn, "atlascloud")
    if atlas_id:
        for cost_config, patterns in _ATLAS_PRICING:
            _upsert_cost(conn, atlas_id, cost_config, *patterns)

    # ── ComfyUI Direct ─────────────────────────────────────────────
    comfy_id = _get_provider_id(conn, "comfyui_direct")
    if comfy_id:
        _upsert_cost(conn, comfy_id, _COMFY_COST, "%")


def downgrade() -> None:
    conn = op.get_bind()
    for ptype in ("poe", "atlascloud", "comfyui_direct"):
        pid = _get_provider_id(conn, ptype)
        if pid:
            conn.execute(
                sa.text("""
                    UPDATE model_configs
                    SET cost_config = NULL
                    WHERE provider_id = CAST(:pid AS uuid)
                """),
                {"pid": pid},
            )
