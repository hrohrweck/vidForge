"""Provider registry for pluggable AI provider discovery and instantiation.

Replaces ad-hoc if/elif chains in factory functions
(`media_generator.get_provider_instance`, `job_router._create_provider_instance`).
Wave 3 of the provider-abstraction plan migrates those factories to this registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

if TYPE_CHECKING:
    from app.services.providers.base import ComfyUIProvider


class ProviderRegistry:
    """In-memory registry mapping provider_type string to provider class.

    `register()` / `get()` / `list_types()` / `has()` are synchronous and cheap.
    `create()` is async because it invokes the provider's `initialize(config)`.
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[ComfyUIProvider]] = {}

    def register(
        self, provider_type: str, provider_class: type[ComfyUIProvider]
    ) -> None:
        if not isinstance(provider_type, str) or not provider_type:
            raise ValueError("provider_type must be a non-empty string")
        self._providers[provider_type] = provider_class

    def get(self, provider_type: str) -> type[ComfyUIProvider]:
        """Return the registered provider class. Raises ValueError if unknown."""
        try:
            return self._providers[provider_type]
        except KeyError as exc:
            raise ValueError(
                f"Unknown provider type: {provider_type}"
            ) from exc

    def has(self, provider_type: str) -> bool:
        return provider_type in self._providers

    def list_types(self) -> list[str]:
        return sorted(self._providers.keys())

    async def create(
        self,
        provider_type: str,
        provider_id: UUID | str,
        config: dict[str, Any],
    ) -> ComfyUIProvider:
        """Instantiate the provider and await its async initialize(config)."""
        provider_class = self.get(provider_type)
        instance = cast(Any, provider_class)(provider_id, config)
        await instance.initialize(config)
        return instance
