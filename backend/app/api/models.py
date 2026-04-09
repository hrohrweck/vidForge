from typing import Any
from fastapi import APIRouter

from app.services.model_registry import get_model, get_all_models, MODELS


router = APIRouter(tags=["models"])


class ModelResponse(dict):
    pass


class ModelDetailResponse(dict):
    pass


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
