from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import User, UserSettings, get_db
from app.services.model_config import (
    get_available_models,
    get_default_model_preferences,
    validate_model_preferences,
)
from app.services.model_registry import get_model, get_all_models, MODELS

router = APIRouter(tags=["models"])


class ModelResponse(dict):
    pass


class ModelDetailResponse(dict):
    pass


class ModelPreferences(BaseModel):
    image_model: str = "flux1-schnell"
    video_model: str = "wan2.2-t2v"
    text_model: str = "qwen3.6:35b"
    image_provider: str = "local"
    video_provider: str = "local"
    text_provider: str = "local"


@router.get("/available")
async def get_available_models_endpoint() -> dict[str, list[dict[str, Any]]]:
    return get_available_models()


@router.get("/preferences")
async def get_model_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings or not settings.preferences:
        return get_default_model_preferences()

    model_prefs = settings.preferences.get("models", {})
    return validate_model_preferences(model_prefs)


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

    validated = validate_model_preferences(prefs.model_dump())

    # Create a new preferences dict to ensure SQLAlchemy detects the change
    current_prefs = dict(settings.preferences) if settings.preferences else {}
    current_prefs["models"] = validated
    settings.preferences = current_prefs

    await db.commit()
    await db.refresh(settings)

    return validated


@router.get("", response_model=list[dict[str, Any]])
async def list_models():
    models = get_all_models()
    return [
        {
            "id": m.id,
            "name": m.name,
            "display_name": m.display_name,
            "provider": m.provider,
            "modality": m.modality,
            "capabilities": m.capabilities,
            "max_duration": m.max_duration,
            "max_resolution": m.max_resolution,
            "default_steps": m.default_steps,
            "distilled": m.distilled,
            "description": m.description,
        }
        for m in models
    ]


@router.get("/capabilities/{capability}", response_model=list[dict[str, Any]])
async def get_models_by_capability(capability: str):
    from app.services.model_registry import get_models_by_capability
    models = get_models_by_capability(capability)
    return [
        {
            "id": m.id,
            "name": m.name,
            "display_name": m.display_name,
            "provider": m.provider,
            "modality": m.modality,
            "capabilities": m.capabilities,
        }
        for m in models
    ]


@router.get("/{model_id}", response_model=dict[str, Any])
async def get_model_details(model_id: str):
    model = get_model(model_id)
    if not model:
        return {"error": "Model not found"}
    
    return {
        "id": model.id,
        "name": model.name,
        "display_name": model.display_name,
        "provider": model.provider,
        "workflow": model.workflow,
        "modality": model.modality,
        "capabilities": model.capabilities,
        "max_duration": model.max_duration,
        "max_resolution": model.max_resolution,
        "default_steps": model.default_steps,
        "distilled": model.distilled,
        "description": model.description,
    }
