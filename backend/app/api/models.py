import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database import ModelConfig, Provider, User, UserSettings, get_db
from app.services.model_config_service import ModelConfigService
from app.services.model_resolver import get_family_variants, is_family_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


# ── Response helpers ────────────────────────────────────────────────


def _model_config_to_dict(m: ModelConfig) -> dict[str, Any]:
    """Convert a ModelConfig ORM object to the legacy API response format."""
    constraints = m.constraints or {}
    cost_config = m.cost_config or None

    # Ensure capabilities have proper accepts_/outputs_ keys based on modality
    caps = m.capabilities
    has_keys: bool
    if isinstance(caps, list):
        has_keys = False
    elif isinstance(caps, dict):
        has_keys = any(k.startswith(("accepts_", "outputs_")) for k in caps)
    else:
        has_keys = False

    if not has_keys:
        modality = m.modality
        inferred: dict[str, bool] = {}
        if modality == "image":
            inferred = {"accepts_text": True, "outputs_image": True}
        elif modality == "video":
            inferred = {"accepts_text": True, "outputs_video": True}
        elif modality == "text":
            inferred = {"accepts_text": True, "outputs_text": True}
        # Merge with existing caps if dict (preserve non-standard keys)
        if isinstance(caps, dict):
            inferred.update(
                {k: v for k, v in caps.items() if not k.startswith(("accepts_", "outputs_"))}
            )
        caps = inferred

    return {
        "id": m.model_id,
        "name": m.model_id,
        "display_name": m.display_name,
        "provider": m.provider.name if m.provider else "local",
        "provider_id": str(m.provider_id) if m.provider_id else None,
        "provider_type": m.provider.provider_type if m.provider else "local",
        "modality": m.modality,
        "capabilities": caps or [],
        "max_duration": constraints.get("max_duration"),
        "max_resolution": constraints.get("max_resolution"),
        "default_steps": constraints.get("default_steps"),
        "distilled": constraints.get("distilled", False),
        "resolutions": constraints.get("resolutions"),
        "size_param_family": constraints.get("size_param_family"),
        "constraints": {
            "supported_aspect_ratios": constraints.get("supported_aspect_ratios"),
            "requires_aspect_ratio": constraints.get("requires_aspect_ratio"),
            "size_param_family": constraints.get("size_param_family"),
            "resolutions": constraints.get("resolutions"),
            "max_duration": constraints.get("max_duration"),
            "max_resolution": constraints.get("max_resolution"),
            "default_steps": constraints.get("default_steps"),
            "distilled": constraints.get("distilled", False),
        },
        "description": (m.extra_params or {}).get("description"),
        "cost_config": cost_config,
        "is_family": is_family_id(m.model_id),
        "variants": get_family_variants(m.model_id) if is_family_id(m.model_id) else {},
    }


# ── Default preferences (runtime lookup) ────────────────────────────

_DEFAULT_MODEL_VALUES: dict[str, str] = {
    "image_model": "flux1-schnell",
    "video_model": "wan2.2",
    "text_model": "qwen3.6:35b",
    "image_provider": "local",
    "video_provider": "local",
    "text_provider": "local",
    "text_to_image_model": "flux1-schnell",
    "image_to_image_model": "flux1-schnell",
    "text_to_video_model": "wan2.2",
    "image_to_video_model": "wan2.2",
}


async def _get_provider_id_by_type(db: AsyncSession, provider_type: str) -> str | None:
    """Look up the first active provider UUID by provider_type."""
    result = await db.execute(
        select(Provider.id).where(
            Provider.provider_type == provider_type,
            Provider.is_active == True,  # noqa: E712
        )
    )
    provider_id = result.scalar_one_or_none()
    return str(provider_id) if provider_id else None


async def get_default_model_preferences(db: AsyncSession) -> dict[str, str]:
    """Return default model preferences with provider IDs looked up at runtime."""
    comfyui_id = await _get_provider_id_by_type(db, "comfyui_direct")
    ollama_id = await _get_provider_id_by_type(db, "ollama")

    defaults = dict(_DEFAULT_MODEL_VALUES)
    defaults["image_provider_id"] = comfyui_id or ""
    defaults["video_provider_id"] = comfyui_id or ""
    defaults["text_provider_id"] = ollama_id or ""
    defaults["text_to_image_provider_id"] = comfyui_id or ""
    defaults["image_to_image_provider_id"] = comfyui_id or ""
    defaults["text_to_video_provider_id"] = comfyui_id or ""
    defaults["image_to_video_provider_id"] = comfyui_id or ""
    return defaults


# ── Validation ─────────────────────────────────────────────────────


async def validate_model_preferences(db: AsyncSession, prefs: dict[str, str]) -> dict[str, str]:
    """Validate model preferences by resolving each (model, provider_id) pair.

    Keeps resolvable values; falls back to defaults with a warning when
    a reference cannot be resolved.
    """
    defaults = await get_default_model_preferences(db)
    validated: dict[str, str] = {}

    model_fields = (
        ("image_model", "image_provider_id"),
        ("video_model", "video_provider_id"),
        ("text_model", "text_provider_id"),
        ("text_to_image_model", "text_to_image_provider_id"),
        ("image_to_image_model", "image_to_image_provider_id"),
        ("text_to_video_model", "text_to_video_provider_id"),
        ("image_to_video_model", "image_to_video_provider_id"),
    )

    for model_field, provider_id_field in model_fields:
        model_id = prefs.get(model_field, defaults.get(model_field, ""))
        provider_id_str = prefs.get(provider_id_field, defaults.get(provider_id_field, ""))

        provider_id: UUID | None = None
        if provider_id_str:
            try:
                provider_id = UUID(provider_id_str)
            except ValueError:
                provider_id = None

        config = await ModelConfigService.resolve_model_config(db, model_id, provider_id)
        if config:
            validated[model_field] = config.model_id
            validated[provider_id_field] = str(config.provider_id)
        else:
            default_model = defaults.get(model_field, "")
            default_provider = defaults.get(provider_id_field, "")
            validated[model_field] = default_model
            validated[provider_id_field] = default_provider
            if model_id and model_id != default_model:
                logger.warning(
                    "Unresolvable model preference %s=%s (provider_id=%s), "
                    "falling back to %s=%s (provider_id=%s)",
                    model_field,
                    model_id,
                    provider_id_str,
                    model_field,
                    default_model,
                    default_provider,
                )

    for provider_field in ("image_provider", "video_provider", "text_provider"):
        validated[provider_field] = prefs.get(provider_field, defaults.get(provider_field, ""))

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


async def get_chat_models(db: AsyncSession) -> list[dict[str, Any]]:
    """Return chat-enabled text models."""
    all_configs = await _list_active_configs(db)
    return [
        _model_config_to_dict(m)
        for m in all_configs
        if m.modality == "text" and getattr(m, "is_chat_enabled", False)
    ]


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


async def get_models_by_capability(db: AsyncSession, capability: str) -> list[dict[str, Any]]:
    """Return all active models that include the given capability."""
    configs = await _list_active_configs(db)
    return [
        _model_config_to_dict(m) for m in configs if m.capabilities and capability in m.capabilities
    ]


# ── Pydantic schemas ────────────────────────────────────────────────


class ModelPreferences(BaseModel):
    image_model: str = "flux1-schnell"
    video_model: str = "wan2.2"
    text_model: str = "qwen3.6:35b"
    image_provider: str = "local"
    video_provider: str = "local"
    text_provider: str = "local"
    text_to_image_model: str = "flux1-schnell"
    image_to_image_model: str = "flux1-schnell"
    text_to_video_model: str = "wan2.2"
    image_to_video_model: str = "wan2.2"
    image_provider_id: str = ""
    video_provider_id: str = ""
    text_provider_id: str = ""
    text_to_image_provider_id: str = ""
    image_to_image_provider_id: str = ""
    text_to_video_provider_id: str = ""
    image_to_video_provider_id: str = ""


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/available")
async def get_available_models_endpoint(
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    return await get_available_models(db)


@router.get("/chat")
async def get_chat_models_endpoint(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await get_chat_models(db)


@router.get("/chat-models")
async def get_chat_models_endpoint_v2(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await get_chat_models(db)


@router.get("/preferences")
async def get_model_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings or not settings.preferences:
        return await get_default_model_preferences(db)

    model_prefs = settings.preferences.get("models", {})
    return await validate_model_preferences(db, model_prefs)


@router.put("/preferences")
async def update_model_preferences(
    prefs: ModelPreferences,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    validated = await validate_model_preferences(db, prefs.model_dump())

    if validated.get("text_to_image_model"):
        validated["image_model"] = validated["text_to_image_model"]
    elif validated.get("image_to_image_model"):
        validated["image_model"] = validated["image_to_image_model"]

    if validated.get("text_to_video_model"):
        validated["video_model"] = validated["text_to_video_model"]
    elif validated.get("image_to_video_model"):
        validated["video_model"] = validated["image_to_video_model"]

    # Create a new preferences dict to ensure SQLAlchemy detects the change
    current_prefs = dict(settings.preferences) if settings.preferences else {}
    current_prefs["models"] = validated
    settings.preferences = current_prefs

    await db.commit()
    await db.refresh(settings)

    return validated


@router.get("", response_model=list[dict[str, Any]])
async def list_models(
    capability: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    models = await get_all_models(db)
    if capability:
        models = [
            m
            for m in models
            if isinstance(m.get("capabilities"), dict) and m["capabilities"].get(capability) is True
        ]
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
            "constraints": m.get("constraints"),
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
            "constraints": m.get("constraints"),
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
        "constraints": model.get("constraints"),
        "description": model["description"],
        "is_family": model.get("is_family", False),
        "variants": model.get("variants", {}),
    }
