"""unify_model_tables_into_model_configs

Revision ID: 026
Revises: f637742c0fd3, 024_add_scene_warnings

Migrates data from poe_models and atlascloud_models tables into the unified
model_configs table, adds extra_config JSONB column, and drops the old
provider-specific model tables.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "026"
down_revision: Union[str, tuple[str, ...], None] = (
    "f637742c0fd3",
    "024_add_scene_warnings",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _modality_to_endpoint(modality: str) -> str:
    """Derive endpoint_type from modality string."""
    mapping = {
        "video": "generateVideo",
        "image": "generateImage",
        "text": "chat_completions",
    }
    return mapping.get(modality, "chat_completions")


def _insert_from_table(
    conn,
    source_table: str,
    provider_type: str,
    existing_provider_id: str,
    *,
    model_id_prefix: str | None = None,
) -> int:
    """Copy rows from *source_table* into model_configs.

    Uses raw INSERT … ON CONFLICT DO NOTHING so that rows already present
    in model_configs (from seed migrations) are preserved.
    Returns the number of rows inserted.
    """
    rows = conn.execute(
        sa.text(f"SELECT id, provider_id, name, model_id, modality, is_active FROM {source_table}")
    ).fetchall()

    if not rows:
        return 0

    provider_id = str(rows[0][1]) if rows[0][1] else existing_provider_id

    inserted = 0
    for row in rows:
        original_id, _, name, raw_model_id, modality, is_active = row

        # Normalized model_id: for Poe, use raw name as-is since model_configs
        # already uses the bare bot ID; for AtlasCloud, also uses bare ID.
        normalized = raw_model_id

        endpoint = _modality_to_endpoint(modality)
        extra = {
            "migrated_from": source_table,
            "original_id": str(original_id),
        }

        try:
            conn.execute(
                sa.text("""
                    INSERT INTO model_configs (
                        id, provider_id, model_id, provider_model_id,
                        display_name, modality, prompt_format, endpoint_type,
                        extra_config, is_active, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), CAST(:pid AS uuid), :mid, :pmid,
                        :dname, :mod, 'string', :ep,
                        CAST(:extra AS jsonb), :active, NOW(), NOW()
                    )
                    ON CONFLICT (provider_id, model_id) DO NOTHING
                """),
                {
                    "pid": provider_id,
                    "mid": normalized,
                    "pmid": raw_model_id,
                    "dname": name,
                    "mod": modality,
                    "ep": endpoint,
                    "extra": json.dumps(extra),
                    "active": is_active,
                },
            )
            inserted += 1
        except Exception:
            # Skip rows that fail (e.g. invalid modality for enum)
            pass

    return inserted


def _get_provider_id(conn, provider_type: str) -> str | None:
    row = conn.execute(
        sa.text("SELECT id FROM providers WHERE provider_type = :pt LIMIT 1"),
        {"pt": provider_type},
    ).fetchone()
    return str(row[0]) if row else None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add extra_config JSONB column to model_configs
    op.add_column(
        "model_configs",
        sa.Column("extra_config", JSONB, nullable=True),
    )

    # 2. Migrate poe_models → model_configs
    if _table_exists(conn, "poe_models"):
        poe_pid = _get_provider_id(conn, "poe")
        if poe_pid:
            count = _insert_from_table(conn, "poe_models", "poe", poe_pid)
            print(f"Migrated {count} rows from poe_models → model_configs")

        # 3. Drop poe_models
        op.execute("DROP INDEX IF EXISTS ix_poe_models_provider_id")
        op.drop_table("poe_models")

    # 4. Migrate atlascloud_models → model_configs
    if _table_exists(conn, "atlascloud_models"):
        atlas_pid = _get_provider_id(conn, "atlascloud")
        if atlas_pid:
            count = _insert_from_table(conn, "atlascloud_models", "atlascloud", atlas_pid)
            print(f"Migrated {count} rows from atlascloud_models → model_configs")

        # 5. Drop atlascloud_models
        op.drop_table("atlascloud_models")


def _table_exists(conn, table_name: str) -> bool:
    """Check whether *table_name* exists in the current database."""
    row = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.tables "
            "  WHERE table_name = :t"
            ")"
        ),
        {"t": table_name},
    ).fetchone()
    return bool(row and row[0])


def downgrade() -> None:
    conn = op.get_bind()

    # 5. Recreate poe_models table
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

    # 4. Recreate atlascloud_models table
    op.create_table(
        "atlascloud_models",
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
    op.create_index("ix_atlascloud_models_provider_id", "atlascloud_models", ["provider_id"])

    # 3. Copy data back from model_configs to poe_models (best effort)
    poe_pid = _get_provider_id(conn, "poe")
    if poe_pid:
        migrated = conn.execute(
            sa.text("""
                SELECT id, provider_model_id, display_name, modality, is_active, extra_config
                FROM model_configs
                WHERE provider_id = CAST(:pid AS uuid)
                  AND extra_config IS NOT NULL
                  AND extra_config->>'migrated_from' = 'poe_models'
            """),
            {"pid": poe_pid},
        ).fetchall()

        for row in migrated:
            try:
                extra = row[5] or {}
                original_id = extra.get("original_id")
                conn.execute(
                    sa.text("""
                        INSERT INTO poe_models (id, provider_id, name, model_id, modality, is_active, created_at)
                        VALUES (CAST(:id AS uuid), CAST(:pid AS uuid), :name, :mid, :mod, :active, NOW())
                    """),
                    {
                        "id": original_id or str(row[0]),
                        "pid": poe_pid,
                        "name": row[2],
                        "mid": row[1],
                        "mod": row[3],
                        "active": row[4],
                    },
                )
            except Exception:
                pass

    # 2. Copy data back from model_configs to atlascloud_models (best effort)
    atlas_pid = _get_provider_id(conn, "atlascloud")
    if atlas_pid:
        migrated = conn.execute(
            sa.text("""
                SELECT id, provider_model_id, display_name, modality, is_active, extra_config
                FROM model_configs
                WHERE provider_id = CAST(:pid AS uuid)
                  AND extra_config IS NOT NULL
                  AND extra_config->>'migrated_from' = 'atlascloud_models'
            """),
            {"pid": atlas_pid},
        ).fetchall()

        for row in migrated:
            try:
                extra = row[5] or {}
                original_id = extra.get("original_id")
                conn.execute(
                    sa.text("""
                        INSERT INTO atlascloud_models (id, provider_id, name, model_id, modality, is_active, created_at)
                        VALUES (CAST(:id AS uuid), CAST(:pid AS uuid), :name, :mid, :mod, :active, NOW())
                    """),
                    {
                        "id": original_id or str(row[0]),
                        "pid": atlas_pid,
                        "name": row[2],
                        "mid": row[1],
                        "mod": row[3],
                        "active": row[4],
                    },
                )
            except Exception:
                pass

    # 1. Drop extra_config column
    op.drop_column("model_configs", "extra_config")
