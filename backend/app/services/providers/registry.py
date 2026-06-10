from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

if TYPE_CHECKING:
    from app.services.providers.base import ComfyUIProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, type[ComfyUIProvider] | str] = {}

    def register(
        self, provider_type: str, provider_class: type[ComfyUIProvider] | str
    ) -> None:
        if not isinstance(provider_type, str) or not provider_type:
            raise ValueError("provider_type must be a non-empty string")
        self._providers[provider_type] = provider_class

    def _resolve(self, provider_type: str) -> type[ComfyUIProvider]:
        entry = self._providers.get(provider_type)
        if entry is None:
            raise ValueError(f"Unknown provider type: {provider_type}")

        if isinstance(entry, str):
            module_path, class_name = entry.rsplit(":", 1)
            try:
                module = import_module(module_path)
            except ImportError as exc:
                raise ValueError(
                    f"provider unavailable: {provider_type} ({exc})"
                ) from exc
            try:
                cls = getattr(module, class_name)
            except AttributeError as exc:
                raise ValueError(
                    f"provider unavailable: {provider_type} — class "
                    f"{class_name!r} not found in {module_path}"
                ) from exc
            self._providers[provider_type] = cls
            return cls  # type: ignore[return-value]

        return entry  # type: ignore[return-value]

    def get(self, provider_type: str) -> type[ComfyUIProvider]:
        return self._resolve(provider_type)

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
        provider_class = self.get(provider_type)
        instance = cast(Any, provider_class)(provider_id, config)
        await instance.initialize(config)
        return instance
