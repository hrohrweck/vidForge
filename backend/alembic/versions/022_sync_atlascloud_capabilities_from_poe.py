"""sync_atlascloud_capabilities_from_poe

Revision ID: 022_sync_atlascloud_capabilities_from_poe
Revises: 021_add_job_chat_link
Create Date: 2026-05-30 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "022_sync_atlascloud_capabilities_from_poe"
down_revision: Union[str, None] = "021_add_job_chat_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Copy capabilities from Poe models to matching AtlasCloud models."""
    conn = op.get_bind()

    poe_models = conn.execute(
        sa.text("""
            SELECT mc.model_id, mc.capabilities
            FROM model_configs mc
            JOIN providers p ON mc.provider_id = p.id
            WHERE p.provider_type = 'poe'
        """)
    ).fetchall()

    atlas_models = conn.execute(
        sa.text("""
            SELECT mc.model_id, mc.id
            FROM model_configs mc
            JOIN providers p ON mc.provider_id = p.id
            WHERE p.provider_type = 'atlascloud'
        """)
    ).fetchall()

    poe_caps = {}
    for model_id, caps in poe_models:
        bare = model_id.replace("poe:", "") if model_id.startswith("poe:") else model_id
        if caps:
            poe_caps[bare] = caps

    atlas_by_bare = {}
    for model_id, mc_id in atlas_models:
        bare = model_id.split("/")[-1] if "/" in model_id else model_id
        atlas_by_bare[bare] = mc_id

    updated = 0
    for bare in set(poe_caps.keys()) & set(atlas_by_bare.keys()):
        caps = poe_caps[bare]
        mc_id = atlas_by_bare[bare]

        conn.execute(
            sa.text("""
                UPDATE model_configs
                SET capabilities = :caps
                WHERE id = :mc_id
            """),
            {"caps": caps, "mc_id": mc_id}
        )
        updated += 1

    print(f"Updated {updated} AtlasCloud model capabilities from Poe counterparts")


def downgrade() -> None:
    """No downgrade — capabilities are additive and safe to keep."""
    pass
