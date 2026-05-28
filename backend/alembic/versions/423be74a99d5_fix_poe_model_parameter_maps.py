"""fix_poe_model_parameter_maps

Revision ID: 423be74a99d5
Revises: e9493c022947
Create Date: 2026-05-28 15:38:31.932529

Data-only fix: UPDATE model_configs for Poe video models with accurate
parameter_map entries so the correct API parameter names are used for
aspect_ratio and duration per model.

Model-specific mappings derived from:
  docs/Provider/Poe/poe-image-video-model-parameters.md

VidForge internal name → Poe API parameter name:
  aspect_ratio → aspect (Veo/Sora), aspect_ratio (Kling/Grok/Pika/Ray), size (Sora-2 alt)
  duration     → seconds (Veo), duration (most others)
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "423be74a99d5"
down_revision: Union[str, None] = "e9493c022947"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_poe_id(conn) -> str | None:
    row = conn.execute(
        sa.text("SELECT id FROM providers WHERE provider_type = 'poe'")
    ).fetchone()
    return str(row[0]) if row else None


def _param(value: dict) -> str:
    """Serialize a dict to JSON for use as a sa.text bound parameter."""
    return json.dumps(value)


# ── parameter_map definitions per model family ──────────────────────

# Veo family: dedicated /v1/videos endpoint.
#   Poe API parameter names: "aspect" (aspect ratio), "seconds" (duration).
_VEO_PARAM_MAP = {"aspect_ratio": "aspect", "duration": "seconds"}

# Sora-2: chat completions with extra_body.
#   Poe API parameter names: "size" (pixel dims), "duration".
_SORA_PARAM_MAP = {"aspect_ratio": "size", "duration": "duration"}

# Kling family (Kling-O3, Kling-v3-Motion-Ctrl, etc.):
#   Same names as VidForge — no translation needed.
_KLING_PARAM_MAP = {"aspect_ratio": "aspect_ratio", "duration": "duration"}

# Grok-Imagine-Video:
#   Same names — no translation.
_GROK_PARAM_MAP = {"aspect_ratio": "aspect_ratio", "duration": "duration"}

# Pika family:
#   Same names — no translation.
_PIKA_PARAM_MAP = {"aspect_ratio": "aspect_ratio", "duration": "duration"}

# Ray 2:
#   Same names — no translation. Resolution in extra_params.
_RAY_PARAM_MAP = {"aspect_ratio": "aspect_ratio", "duration": "duration"}

# Dream Machine (Luma AI):
#   Same names.
_LUMA_PARAM_MAP = {"aspect_ratio": "aspect_ratio", "duration": "duration"}

# Runway Gen-4 Turbo:
#   Duration configurable; aspect ratio appears not exposed separately.
_RUNWAY_PARAM_MAP = {"duration": "duration"}

# Hailuo AI / Hailuo Live:
#   Duration configurable; resolution fixed internally.
_HAILUO_PARAM_MAP = {"duration": "duration"}


# ── extra_params definitions (provider-specific defaults) ───────────

def _ep(value: dict) -> str:
    """Serialize a dict to JSON for use as a sa.text bound parameter."""
    return json.dumps(value)


_VEO_1080P_EXTRA = {"resolution": "1080p"}
_VEO_720P_EXTRA = {"resolution": "720p"}
# Grok and Ray 2 also accept a resolution parameter.
_GROK_EXTRA = {"resolution": "720p"}
_RAY_EXTRA = {"resolution": "720p"}


def _update_models(
    conn,
    poe_id: str,
    param_map: dict,
    extra_params: dict | None,
    model_ids: list[str],
) -> None:
    """UPDATE parameter_map and optionally extra_params for a list of model_ids."""
    ids = ", ".join(f"'{m}'" for m in model_ids)
    pmap = _param(param_map)
    conn.execute(
        sa.text(f"""
            UPDATE model_configs
            SET parameter_map = CAST(:pmap AS jsonb)
            WHERE provider_id = CAST(:pid AS uuid)
              AND LOWER(model_id) IN ({ids})
        """),
        {"pmap": pmap, "pid": poe_id},
    )
    if extra_params:
        eps = _ep(extra_params)
        conn.execute(
            sa.text(f"""
                UPDATE model_configs
                SET extra_params = CAST(:eparams AS jsonb)
                WHERE provider_id = CAST(:pid AS uuid)
                  AND LOWER(model_id) IN ({ids})
            """),
            {"eparams": eps, "pid": poe_id},
        )


def upgrade() -> None:
    conn = op.get_bind()
    poe_id = _get_poe_id(conn)
    if not poe_id:
        return  # Poe provider not configured — nothing to fix

    # ── Veo family (video_endpoint) ─────────────────────────────────
    # Full-quality Veo models (1080p default)
    _update_models(
        conn, poe_id, _VEO_PARAM_MAP, _VEO_1080P_EXTRA,
        [
            "veo-3.1", "veo-3.1-lite", "veo-v3.1",
            "veo-3", "veo-2", "veo-2-video",
        ],
    )
    # Fast / lower-quality variants (720p default)
    _update_models(
        conn, poe_id, _VEO_PARAM_MAP, _VEO_720P_EXTRA,
        [
            "veo-3.1-fast", "veo-3-fast", "veo-3-vfast",
            "veo-v3.1-fast",
        ],
    )

    # ── Sora-2 ─────────────────────────────────────────────────────
    _update_models(
        conn, poe_id, _SORA_PARAM_MAP, None,
        ["sora-2", "sora-2-turbo", "sora-2-pro"],
    )

    # ── Kling family ────────────────────────────────────────────────
    _update_models(
        conn, poe_id, _KLING_PARAM_MAP, None,
        [
            "kling-o3", "kling-o1", "kling-o2",
            "kling-v3-motion-ctrl", "kling-v3-motion",
            "kling-pro", "kling-1.6",
        ],
    )

    # ── Grok-Imagine-Video ──────────────────────────────────────────
    _update_models(
        conn, poe_id, _GROK_PARAM_MAP, _GROK_EXTRA,
        ["grok-imagine-video", "grok-video", "grok-imagine-2"],
    )

    # ── Pika family ─────────────────────────────────────────────────
    _update_models(
        conn, poe_id, _PIKA_PARAM_MAP, None,
        ["pika-2.0", "pika-2.1", "pika-2.2", "pika-2"],
    )

    # ── Ray 2 ───────────────────────────────────────────────────────
    _update_models(
        conn, poe_id, _RAY_PARAM_MAP, _RAY_EXTRA,
        ["ray-2", "ray2"],
    )

    # ── Dream Machine (Luma AI) ─────────────────────────────────────
    _update_models(
        conn, poe_id, _LUMA_PARAM_MAP, None,
        ["dream-machine", "dream-machine-v1"],
    )

    # ── Runway Gen-4 Turbo ──────────────────────────────────────────
    _update_models(
        conn, poe_id, _RUNWAY_PARAM_MAP, None,
        ["runway-gen-4-turbo", "gen-4-turbo"],
    )

    # ── Hailuo AI ───────────────────────────────────────────────────
    _update_models(
        conn, poe_id, _HAILUO_PARAM_MAP, None,
        ["hailuo-ai", "hailuo-live", "hailuo-01", "hailuo-02"],
    )


def downgrade() -> None:
    """Set parameter_map and extra_params to NULL for Poe providers.

    Cannot restore original values because the original seed migration
    set these columns to NULL — so resetting to NULL is the correct
    downgrade behaviour.
    """
    conn = op.get_bind()
    poe_id = _get_poe_id(conn)
    if not poe_id:
        return

    conn.execute(
        sa.text("""
            UPDATE model_configs
            SET parameter_map = NULL,
                extra_params   = NULL
            WHERE provider_id = CAST(:pid AS uuid)
        """),
        {"pid": poe_id},
    )
