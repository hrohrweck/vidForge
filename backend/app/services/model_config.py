"""Model configuration management for user preferences."""

from typing import Any

# Available image generation models
AVAILABLE_IMAGE_MODELS = [
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
    {
        "id": "poe-gpt-image",
        "name": "GPT-Image-1 (Poe)",
        "description": "Cloud-based image generation via Poe API.",
        "size_gb": 0,
        "speed": "cloud",
        "quality": "excellent",
        "license": "Proprietary",
        "provider": "poe",
        "comfyui_workflow": None,
        "default": False,
    },
]

# Available video generation models
AVAILABLE_VIDEO_MODELS = [
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
    {
        "id": "poe-veo",
        "name": "Veo-3.1 (Poe)",
        "description": "Cloud-based video generation via Poe API.",
        "size_gb": 0,
        "speed": "cloud",
        "quality": "excellent",
        "license": "Proprietary",
        "provider": "poe",
        "comfyui_workflow": None,
        "default": False,
    },
]

# Available text generation models (for story creation, scene planning, etc.)
AVAILABLE_TEXT_MODELS = [
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
    """Get all available models for user selection."""
    return {
        "image_models": AVAILABLE_IMAGE_MODELS,
        "video_models": AVAILABLE_VIDEO_MODELS,
        "text_models": AVAILABLE_TEXT_MODELS,
    }


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
    for model in AVAILABLE_IMAGE_MODELS + AVAILABLE_VIDEO_MODELS + AVAILABLE_TEXT_MODELS:
        if model["id"] == model_id:
            return model
    return None


def validate_model_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize model preferences."""
    defaults = get_default_model_preferences()
    validated = {}

    image_model = preferences.get("image_model", defaults["image_model"])
    if get_model_config(image_model):
        validated["image_model"] = image_model
    else:
        validated["image_model"] = defaults["image_model"]

    video_model = preferences.get("video_model", defaults["video_model"])
    if get_model_config(video_model):
        validated["video_model"] = video_model
    else:
        validated["video_model"] = defaults["video_model"]

    text_model = preferences.get("text_model", defaults["text_model"])
    if get_model_config(text_model):
        validated["text_model"] = text_model
    else:
        validated["text_model"] = defaults["text_model"]

    validated["image_provider"] = preferences.get("image_provider", defaults["image_provider"])
    validated["video_provider"] = preferences.get("video_provider", defaults["video_provider"])
    validated["text_provider"] = preferences.get("text_provider", defaults["text_provider"])

    return validated
