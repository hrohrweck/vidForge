"""Model configuration management for user preferences."""

from __future__ import annotations

from typing import Any

# Static local models — always available
AVAILABLE_IMAGE_MODELS: list[dict[str, Any]] = [
    {
        "id": "flux1-schnell",
        "name": "FLUX.1-schnell",
        "description": "High-quality image generation with excellent prompt adherence. 1-4 steps.",
        "size_gb": 23,
        "speed": "fast",
        "quality": "excellent",
        "license": "Apache 2.0",
        "provider": "local",
        "comfyui_workflow": "flux_image.json",
        "default": True,
    },
    {
        "id": "sdxl",
        "name": "Stable Diffusion XL",
        "description": "Good quality, faster generation, lower VRAM usage.",
        "size_gb": 6.5,
        "speed": "very_fast",
        "quality": "good",
        "license": "OpenRAIL",
        "provider": "local",
        "comfyui_workflow": "sdxl_image.json",
        "default": False,
    },
]

AVAILABLE_VIDEO_MODELS: list[dict[str, Any]] = [
    {
        "id": "wan2.2-t2v",
        "name": "Wan 2.2 T2V",
        "description": "Text-to-video generation. Good quality, moderate speed.",
        "size_gb": 16.7,
        "speed": "moderate",
        "quality": "good",
        "license": "Apache 2.0",
        "provider": "local",
        "comfyui_workflow": "wan_t2v.json",
        "default": True,
    },
    {
        "id": "ltx2.3-t2v",
        "name": "LTX 2.3 T2V",
        "description": "High-quality video generation. Very large model.",
        "size_gb": 43,
        "speed": "slow",
        "quality": "excellent",
        "license": "Proprietary",
        "provider": "local",
        "comfyui_workflow": "ltx_t2v.json",
        "default": False,
    },
]

AVAILABLE_TEXT_MODELS: list[dict[str, Any]] = [
    {
        "id": "qwen3.6:35b",
        "name": "Qwen 3.6 (35B)",
        "description": "Large language model for story creation, scene planning, and prompt enhancement. Runs locally via Ollama.",
        "size_gb": 22,
        "speed": "moderate",
        "quality": "excellent",
        "license": "Apache 2.0",
        "provider": "local",
        "ollama_model": "qwen3.6:35b",
        "default": True,
    },
    {
        "id": "llama3.3:70b",
        "name": "Llama 3.3 (70B)",
        "description": "Meta's largest open weights model. Excellent reasoning and creativity.",
        "size_gb": 40,
        "speed": "slow",
        "quality": "excellent",
        "license": "Llama 3.3",
        "provider": "local",
        "ollama_model": "llama3.3:70b",
        "default": False,
    },
    {
        "id": "qwen3.6:14b",
        "name": "Qwen 3.6 (14B)",
        "description": "Faster alternative with good quality for most text generation tasks.",
        "size_gb": 9,
        "speed": "fast",
        "quality": "good",
        "license": "Apache 2.0",
        "provider": "local",
        "ollama_model": "qwen3.6:14b",
        "default": False,
    },
    {
        "id": "huihui_ai/qwen3.6-abliterated:35b-Claude-4.7",
        "name": "Qwen 3.6 Abliterated (35B)",
        "description": "Uncensored variant with enhanced creative capabilities.",
        "size_gb": 22,
        "speed": "moderate",
        "quality": "excellent",
        "license": "Apache 2.0",
        "provider": "local",
        "ollama_model": "huihui_ai/qwen3.6-abliterated:35b-Claude-4.7",
        "default": False,
    },
]


def get_available_models() -> dict[str, list[dict[str, Any]]]:
    """Get all available models for user selection.

    Returns the static local models **plus** any Poe models registered
    in the database, merged dynamically so the UI always shows the
    full list.
    """
    image_models = list(AVAILABLE_IMAGE_MODELS)
    video_models = list(AVAILABLE_VIDEO_MODELS)
    text_models = list(AVAILABLE_TEXT_MODELS)

    try:
        poe_image, poe_video, poe_text = _load_poe_models()
        image_models.extend(poe_image)
        video_models.extend(poe_video)
        text_models.extend(poe_text)
    except Exception:
        pass  # DB not available (e.g. during tests)

    return {
        "image_models": image_models,
        "video_models": video_models,
        "text_models": text_models,
    }


def _load_poe_models() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
]:
    """Load active Poe models from the database (sync, short-lived connection)."""
    from sqlalchemy import create_engine, text

    from app.config import get_settings

    settings = get_settings()
    db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    if "+psycopg2" not in db_url and "postgresql://" in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://")

    images: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT model_id, name, modality FROM poe_models WHERE is_active = true")
            ).fetchall()
            for model_id, name, modality in rows:
                entry = {
                    "id": f"poe:{model_id}",
                    "name": f"{name} (Poe)",
                    "description": f"Poe API model: {model_id}",
                    "size_gb": 0,
                    "speed": "cloud",
                    "quality": "good",
                    "license": "Proprietary",
                    "provider": "poe",
                    "poe_model_id": model_id,
                    "default": False,
                }
                if modality == "image":
                    images.append(entry)
                elif modality == "video":
                    videos.append(entry)
                elif modality == "text":
                    texts.append(entry)
    finally:
        engine.dispose()

    return images, videos, texts


def get_default_model_preferences() -> dict[str, str]:
    """Get default model preferences."""
    return {
        "image_model": "flux1-schnell",
        "video_model": "wan2.2-t2v",
        "text_model": "qwen3.6:35b",
        "image_provider": "local",
        "video_provider": "local",
        "text_provider": "local",
    }


def get_model_config(model_id: str) -> dict[str, Any] | None:
    """Get configuration for a specific model."""
    all_models = (
        AVAILABLE_IMAGE_MODELS + AVAILABLE_VIDEO_MODELS + AVAILABLE_TEXT_MODELS
    )
    for model in all_models:
        if model["id"] == model_id:
            return model

    try:
        poe_img, poe_vid, poe_txt = _load_poe_models()
        for model in poe_img + poe_vid + poe_txt:
            if model["id"] == model_id:
                return model
    except Exception:
        pass

    return None


def validate_model_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize model preferences."""
    defaults = get_default_model_preferences()
    validated: dict[str, Any] = {}

    all_models = get_available_models()
    all_ids = (
        {m["id"] for m in all_models["image_models"]}
        | {m["id"] for m in all_models["video_models"]}
        | {m["id"] for m in all_models["text_models"]}
    )

    for key, default in [
        ("image_model", defaults["image_model"]),
        ("video_model", defaults["video_model"]),
        ("text_model", defaults["text_model"]),
    ]:
        val = preferences.get(key, default)
        validated[key] = val if val in all_ids else default

    validated["image_provider"] = preferences.get(
        "image_provider", defaults["image_provider"]
    )
    validated["video_provider"] = preferences.get(
        "video_provider", defaults["video_provider"]
    )
    validated["text_provider"] = preferences.get(
        "text_provider", defaults["text_provider"]
    )

    return validated
