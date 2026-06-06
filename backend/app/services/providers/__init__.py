from app.services.providers.atlascloud import AtlasCloudProvider
from app.services.providers.base import ComfyUIProvider, ProviderInfo
from app.services.providers.comfyui_direct import ComfyUIDirectProvider
from app.services.providers.ollama import OllamaProvider
from app.services.providers.poe import PoeProvider
from app.services.providers.registry import ProviderRegistry
from app.services.providers.runpod import RunPodProvider

registry = ProviderRegistry()
registry.register("atlascloud", AtlasCloudProvider)
registry.register("comfyui_direct", ComfyUIDirectProvider)
registry.register("ollama", OllamaProvider)
registry.register("poe", PoeProvider)
registry.register("runpod", RunPodProvider)

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
