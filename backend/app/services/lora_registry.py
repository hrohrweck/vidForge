"""LoRA model registry for avatar character consistency.

Stores mappings from avatar IDs to trained LoRA model paths so that
image generation can load the correct LoRA when an avatar's
consistency_strategy is "lora" and training has completed.
"""

from typing import Any

_registry: dict[str, dict[str, Any]] = {}


def register_lora(
    avatar_id: str,
    lora_path: str,
    base_model: str = "flux1-schnell",
) -> None:
    """Register a trained LoRA model for an avatar."""
    _registry[avatar_id] = {"path": lora_path, "base_model": base_model}


def get_lora(avatar_id: str) -> dict[str, Any] | None:
    """Return LoRA info for an avatar, or None if not registered."""
    return _registry.get(avatar_id)


def unregister_lora(avatar_id: str) -> None:
    """Remove a LoRA registration."""
    _registry.pop(avatar_id, None)


def has_lora(avatar_id: str) -> bool:
    """Check whether an avatar has a registered LoRA model."""
    return avatar_id in _registry
