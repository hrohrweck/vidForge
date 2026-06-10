from __future__ import annotations

from importlib import import_module
from typing import Any

from app.services.providers.base import ComfyUIProvider, ProviderInfo
from app.services.providers.registry import ProviderRegistry

registry = ProviderRegistry()
for provider_type, provider_target in {
    "atlascloud": "app.services.providers.atlascloud:AtlasCloudProvider",
    "comfyui_direct": "app.services.providers.comfyui_direct:ComfyUIDirectProvider",
    "ollama": "app.services.providers.ollama:OllamaProvider",
    "poe": "app.services.providers.poe:PoeProvider",
    "runpod": "app.services.providers.runpod:RunPodProvider",
}.items():
    registry.register(provider_type, provider_target)

_PROVIDER_ATTRS = {
    "AtlasCloudProvider": ("app.services.providers.atlascloud", "AtlasCloudProvider"),
    "ComfyUIDirectProvider": ("app.services.providers.comfyui_direct", "ComfyUIDirectProvider"),
    "OllamaProvider": ("app.services.providers.ollama", "OllamaProvider"),
    "PoeProvider": ("app.services.providers.poe", "PoeProvider"),
    "RunPodProvider": ("app.services.providers.runpod", "RunPodProvider"),
}


__all__ = [
    "AtlasCloudProvider",
    "ComfyUIProvider",
    "ComfyUIDirectProvider",
    "OllamaProvider",
    "PoeProvider",
    "ProviderInfo",
    "ProviderRegistry",
    "RunPodProvider",
    "registry",
]


def __getattr__(name: str) -> Any:
    if name in _PROVIDER_ATTRS:
        module_path, class_name = _PROVIDER_ATTRS[name]
        module = import_module(module_path)
        value = getattr(module, class_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
