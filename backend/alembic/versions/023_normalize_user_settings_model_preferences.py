"""normalize_user_settings_model_preferences

Revision ID: 023_normalize_user_settings_model_preferences
Revises: 022_sync_atlascloud_capabilities_from_poe
Create Date: 2026-05-31 00:00:00.000000
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "023_normalize_user_settings"
down_revision: Union[str, None] = "d01e4f5b6c70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

LEGACY_PREFIXES = ("atlascloud:", "poe:")

MODEL_FIELDS: dict[str, str] = {
    "image_model": "image_provider_id",
    "video_model": "video_provider_id",
    "text_model": "text_provider_id",
    "text_to_image_model": "text_to_image_provider_id",
    "image_to_image_model": "image_to_image_provider_id",
    "text_to_video_model": "text_to_video_provider_id",
    "image_to_video_model": "image_to_video_provider_id",
}

FIELD_PROVIDER_PRIORITY: dict[str, tuple[str, ...]] = {
    "image_model": ("comfyui_direct", "atlascloud", "poe"),
    "video_model": ("comfyui_direct", "atlascloud", "poe"),
    "text_model": ("ollama", "atlascloud", "poe"),
    "text_to_image_model": ("comfyui_direct", "atlascloud", "poe"),
    "image_to_image_model": ("comfyui_direct", "atlascloud", "poe"),
    "text_to_video_model": ("comfyui_direct", "atlascloud", "poe"),
    "image_to_video_model": ("comfyui_direct", "atlascloud", "poe"),
}


class ModelLookup:
    def __init__(self, conn: sa.Connection) -> None:
        self.providers_by_type = self._load_providers(conn)
        self.models = self._load_models(conn)

    @staticmethod
    def _load_providers(conn: sa.Connection) -> dict[str, str]:
        rows = conn.execute(
            sa.text("SELECT id, provider_type FROM providers")
        ).fetchall()
        providers: dict[str, str] = {}
        for row in rows:
            data = row._mapping
            provider_type = data["provider_type"]
            providers.setdefault(provider_type, str(data["id"]))
        return providers

    @staticmethod
    def _load_models(conn: sa.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            sa.text(
                """
                SELECT
                    mc.model_id,
                    mc.provider_model_id,
                    mc.provider_id,
                    p.provider_type
                FROM model_configs mc
                JOIN providers p ON p.id = mc.provider_id
                """
            )
        ).fetchall()
        return [dict(row._mapping) for row in rows]

    def resolve(
        self,
        value: str,
        field: str,
    ) -> tuple[str, str] | None:
        if value.startswith("atlascloud:"):
            stripped = value.removeprefix("atlascloud:")
            return self._resolve_atlascloud(stripped)

        if value.startswith("poe:"):
            stripped = value.removeprefix("poe:")
            return self._resolve_poe(stripped)

        return self._resolve_bare(value, field)

    def _resolve_atlascloud(self, value: str) -> tuple[str, str] | None:
        provider_id = self.providers_by_type.get("atlascloud")
        if not provider_id:
            return None

        candidates = (
            self._find_exact_model_id(value, provider_id)
            or self._find_exact_provider_model_id(value, provider_id)
            or self._find_exact_model_id(f"atlascloud/{value}", provider_id)
            or self._find_unique_suffix(value, provider_id)
        )
        if candidates:
            return candidates["model_id"], str(candidates["provider_id"])
        return None

    def _resolve_poe(self, value: str) -> tuple[str, str] | None:
        provider_id = self.providers_by_type.get("poe")
        if not provider_id:
            return None

        candidate = (
            self._find_exact_model_id(value, provider_id)
            or self._find_exact_provider_model_id(value, provider_id)
        )
        if candidate:
            return candidate["model_id"], str(candidate["provider_id"])
        return None

    def _resolve_bare(self, value: str, field: str) -> tuple[str, str] | None:
        exact_matches = [model for model in self.models if model["model_id"] == value]
        if len(exact_matches) == 1:
            match = exact_matches[0]
            return match["model_id"], str(match["provider_id"])

        for provider_type in FIELD_PROVIDER_PRIORITY[field]:
            provider_id = self.providers_by_type.get(provider_type)
            if not provider_id:
                continue
            match = self._find_exact_model_id(value, provider_id)
            if match:
                return match["model_id"], str(match["provider_id"])

        provider_matches = [
            model for model in self.models if model["provider_model_id"] == value
        ]
        if len(provider_matches) == 1:
            match = provider_matches[0]
            return match["model_id"], str(match["provider_id"])

        return None

    def _find_exact_model_id(
        self,
        model_id: str,
        provider_id: str,
    ) -> dict[str, Any] | None:
        for model in self.models:
            if model["model_id"] == model_id and str(model["provider_id"]) == provider_id:
                return model
        return None

    def _find_exact_provider_model_id(
        self,
        provider_model_id: str,
        provider_id: str,
    ) -> dict[str, Any] | None:
        for model in self.models:
            if (
                model["provider_model_id"] == provider_model_id
                and str(model["provider_id"]) == provider_id
            ):
                return model
        return None

    def _find_unique_suffix(
        self,
        value: str,
        provider_id: str,
    ) -> dict[str, Any] | None:
        suffixes = [value]
        final_segment = value.rsplit("/", 1)[-1]
        if final_segment != value:
            suffixes.append(final_segment)

        for suffix in suffixes:
            matches = [
                model
                for model in self.models
                if str(model["provider_id"]) == provider_id
                and (
                    model["model_id"].endswith(suffix)
                    or model["provider_model_id"].endswith(suffix)
                )
            ]
            if len(matches) == 1:
                return matches[0]

        return None


def _has_legacy_prefix(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(LEGACY_PREFIXES)


def _is_already_normalized(models: dict[str, Any]) -> bool:
    for field in MODEL_FIELDS:
        if _has_legacy_prefix(models.get(field)):
            return False

    model_fields_present = [field for field in MODEL_FIELDS if models.get(field)]
    if not model_fields_present:
        return False

    return all(models.get(MODEL_FIELDS[field]) for field in model_fields_present)


def _normalize_models(
    user_id: str,
    models: dict[str, Any],
    lookup: ModelLookup,
) -> tuple[dict[str, Any], bool]:
    normalized = copy.deepcopy(models)
    changed = False

    for field, provider_field in MODEL_FIELDS.items():
        value = normalized.get(field)
        if not isinstance(value, str) or not value:
            continue

        try:
            resolved = lookup.resolve(value, field)
        except Exception as exc:  # noqa: BLE001 - keep one bad field from aborting migration
            logger.warning(
                "Could not resolve user_settings %s models.%s=%r: %s",
                user_id,
                field,
                value,
                exc,
            )
            continue

        if not resolved:
            logger.warning(
                "Leaving unresolved user_settings %s models.%s=%r unchanged",
                user_id,
                field,
                value,
            )
            continue

        model_id, provider_id = resolved
        old_provider_id = normalized.get(provider_field)
        field_changed = value != model_id or old_provider_id != provider_id

        if field_changed:
            normalized[field] = model_id
            normalized[provider_field] = provider_id
            changed = True
            logger.info(
                "Normalized user_settings %s models.%s %r -> %r and %s %r -> %r",
                user_id,
                field,
                value,
                model_id,
                provider_field,
                old_provider_id,
                provider_id,
            )

    return normalized, changed


def upgrade() -> None:
    conn = op.get_bind()
    lookup = ModelLookup(conn)

    rows = conn.execute(
        sa.text("SELECT user_id, preferences FROM user_settings WHERE preferences IS NOT NULL")
    ).fetchall()

    update_stmt = sa.text(
        "UPDATE user_settings SET preferences = :preferences WHERE user_id = :user_id"
    ).bindparams(sa.bindparam("preferences", type_=JSONB))

    updated = 0
    skipped = 0
    for row in rows:
        data = row._mapping
        user_id = str(data["user_id"])
        preferences = copy.deepcopy(data["preferences"])
        if not isinstance(preferences, dict):
            continue

        models = preferences.get("models")
        if not isinstance(models, dict):
            continue

        if _is_already_normalized(models):
            skipped += 1
            continue

        normalized_models, changed = _normalize_models(user_id, models, lookup)
        if not changed:
            continue

        preferences["models"] = normalized_models
        conn.execute(update_stmt, {"user_id": user_id, "preferences": preferences})
        updated += 1

    logger.info(
        "Normalized model preferences for %s user_settings rows; skipped %s rows",
        updated,
        skipped,
    )


def downgrade() -> None:
    """No-op downgrade: keep normalized model references and provider IDs intact."""
    logger.info("Downgrade is a no-op for normalized user_settings model preferences")
