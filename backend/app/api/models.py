from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database import ModelConfig, User, UserSettings, get_db
from app.services.model_config_service import ModelConfigService
from app.services.model_resolver import get_all_families, get_family_variants, is_family_id

router = APIRouter(tags=["models"])


# ── Response helpers ────────────────────────────────────────────────


def _model_config_to_dict(m: ModelConfig) -> dict[str, Any]:
    """Convert a ModelConfig ORM object to the legacy API response format."""
    constraints = m.constraints or {}
    return {
        "id": m.model_id,
        "name": m.model_id,
        "display_name": m.display_name,
        "provider": m.provider.name if m.provider else "local",
        "provider_id": str(m.provider_id) if m.provider_id else None,
        "provider_type": m.provider.provider_type if m.provider else "local",
        "modality": m.modality,
        "capabilities": m.capabilities or [],
        "max_duration": constraints.get("max_duration"),
        "max_resolution": constraints.get("max_resolution"),
        "default_steps": constraints.get("default_steps"),
        "distilled": constraints.get("distilled", False),
        "description": (m.extra_params or {}).get("description"),
        "is_family": is_family_id(m.model_id),
        "variants": get_family_variants(m.model_id) if is_family_id(m.model_id) else {},
    }


# ── Default preferences (static fallback) ──────────────────────────

_DEFAULT_MODEL_PREFERENCES: dict[str, str] = {
    "image_model": "flux1-schnell",
    "video_model": "wan2.2",
    "text_model": "qwen3.6:35b",
    "image_provider": "local",
    "video_provider": "local",
    "text_provider": "local",
}


def get_default_model_preferences() -> dict[str, str]:
    """Return static default model preferences."""
    return dict(_DEFAULT_MODEL_PREFERENCES)


# ── Validation ─────────────────────────────────────────────────────


async def _get_valid_model_ids(db: AsyncSession) -> set[str]:
    """Return the set of all active model_ids."""
    result = await db.execute(
        select(ModelConfig.model_id).where(ModelConfig.is_active == True)  # noqa: E712
    )
    return {row[0] for row in result.all()}


async def validate_model_preferences(
    db: AsyncSession, prefs: dict[str, str]
) -> dict[str, str]:
    """Validate model preferences against currently active models in DB."""
    valid_ids = await _get_valid_model_ids(db)
    validated: dict[str, str] = {}
    for field in ("image_model", "video_model", "text_model"):
        value = prefs.get(field, _DEFAULT_MODEL_PREFERENCES.get(field, ""))
        if value in valid_ids:
            validated[field] = value
        else:
            validated[field] = _DEFAULT_MODEL_PREFERENCES.get(field, "")
    return validated


# ── Query helpers ───────────────────────────────────────────────────


async def _list_active_configs(db: AsyncSession) -> list[ModelConfig]:
    """Return all active ModelConfig rows with their provider eagerly loaded."""
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.is_active == True)  # noqa: E712
        .options(selectinload(ModelConfig.provider))
    )
    return list(result.scalars().all())


async def get_available_models(db: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    """Return models grouped by modality, matching the legacy response shape."""
    all_configs = await _list_active_configs(db)
    groups: dict[str, list[dict[str, Any]]] = {
        "image_models": [],
        "video_models": [],
        "text_models": [],
    }
    for cfg in all_configs:
        if cfg.modality == "image":
            groups["image_models"].append(_model_config_to_dict(cfg))
        elif cfg.modality == "video":
            groups["video_models"].append(_model_config_to_dict(cfg))
        elif cfg.modality == "text":
            groups["text_models"].append(_model_config_to_dict(cfg))
    return groups


async def get_all_models(db: AsyncSession) -> list[dict[str, Any]]:
    """Return all active models as dicts."""
    configs = await _list_active_configs(db)
    return [_model_config_to_dict(m) for m in configs]


async def get_model(db: AsyncSession, model_id: str) -> dict[str, Any] | None:
    """Look up a model by model_id string."""
    result = await db.execute(
        select(ModelConfig)
        .where(
            ModelConfig.model_id == model_id,
            ModelConfig.is_active == True,  # noqa: E712
        )
        .options(selectinload(ModelConfig.provider))
    )
    cfg = result.scalars().first()
    if cfg is None:
        return None
    return _model_config_to_dict(cfg)


async def get_models_by_capability(
    db: AsyncSession, capability: str
) -> list[dict[str, Any]]:
    """Return all active models that include the given capability."""
    configs = await _list_active_configs(db)
    return [
        _model_config_to_dict(m)
        for m in configs
        if m.capabilities and capability in m.capabilities
    ]


# ── Pydantic schemas ────────────────────────────────────────────────


class ModelPreferences(BaseModel):
    image_model: str = "flux1-schnell"
    video_model: str = "wan2.2"
    text_model: str = "qwen3.6:35b"
    image_provider: str = "local"
    video_provider: str = "local"
    text_provider: str = "local"


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/available")
async def get_available_models_endpoint(
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    return await get_available_models(db)


@router.get("/preferences")
async def get_model_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()

    if not settings or not settings.preferences:
        return get_default_model_preferences()

    model_prefs = settings.preferences.get("models", {})
    return await validate_model_preferences(db, model_prefs)


@router.put("/preferences")
async def update_model_preferences(
    prefs: ModelPreferences,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    validated = await validate_model_preferences(db, prefs.model_dump())

    # Create a new preferences dict to ensure SQLAlchemy detects the change
    current_prefs = dict(settings.preferences) if settings.preferences else {}
    current_prefs["models"] = validated
    settings.preferences = current_prefs

    await db.commit()
    await db.refresh(settings)

    return validated


@router.get("", response_model=list[dict[str, Any]])
async def list_models(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    models = await get_all_models(db)
    # Include only the fields the frontend expects
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "display_name": m["display_name"],
            "provider": m["provider"],
            "modality": m["modality"],
            "capabilities": m["capabilities"],
            "max_duration": m["max_duration"],
            "max_resolution": m["max_resolution"],
            "default_steps": m["default_steps"],
            "distilled": m["distilled"],
            "description": m["description"],
        }
        for m in models
    ]


@router.get("/capabilities/{capability}", response_model=list[dict[str, Any]])
async def get_models_by_capability_endpoint(
    capability: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    models = await get_models_by_capability(db, capability)
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "display_name": m["display_name"],
            "provider": m["provider"],
            "modality": m["modality"],
            "capabilities": m["capabilities"],
        }
        for m in models
    ]


@router.get("/{model_id}", response_model=dict[str, Any])
async def get_model_details(
    model_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    model = await get_model(db, model_id)
    if not model:
        return {"error": "Model not found"}

    return {
        "id": model["id"],
        "name": model["name"],
        "display_name": model["display_name"],
        "provider": model["provider"],
        "workflow": model.get("comfyui_workflow"),
        "modality": model["modality"],
        "capabilities": model["capabilities"],
        "max_duration": model["max_duration"],
        "max_resolution": model["max_resolution"],
        "default_steps": model["default_steps"],
        "distilled": model["distilled"],
        "description": model["description"],
        "is_family": model.get("is_family", False),
        "variants": model.get("variants", {}),
    }
