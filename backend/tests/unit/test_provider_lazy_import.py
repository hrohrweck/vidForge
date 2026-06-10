"""Tests that provider imports are lazy — the registry must not load
provider submodules until they are actually needed.
"""
from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any, cast
from uuid import uuid4

import pytest


PROVIDER_MODULES = {
    "app.services.providers.atlascloud",
    "app.services.providers.comfyui_direct",
    "app.services.providers.ollama",
    "app.services.providers.poe",
    "app.services.providers.runpod",
}


def _is_provider_submodule_loaded() -> bool:
    return any(mod in sys.modules for mod in PROVIDER_MODULES)


def _unload_providers() -> None:
    for mod in list(sys.modules.keys()):
        if any(mod.startswith(prefix) for prefix in PROVIDER_MODULES):
            del sys.modules[mod]
    if "app.services.providers" in sys.modules:
        del sys.modules["app.services.providers"]


class TestLazyImports:
    @pytest.fixture(autouse=True)
    def _clean_modules(self) -> Iterator[None]:
        _unload_providers()
        yield
        _unload_providers()

    def test_import_providers_package_does_not_load_submodules(self) -> None:
        assert not _is_provider_submodule_loaded()
        import app.services.providers  # noqa: F401
        assert not _is_provider_submodule_loaded()

    def test_import_providers_package_keeps_registry_available(self) -> None:
        import app.services.providers as providers

        assert providers.registry.list_types() == [
            "atlascloud",
            "comfyui_direct",
            "ollama",
            "poe",
            "runpod",
        ]
        assert not _is_provider_submodule_loaded()

    def test_registry_list_types_does_not_load_submodules(self) -> None:
        assert not _is_provider_submodule_loaded()
        from app.services.providers import registry
        types = registry.list_types()
        assert set(types) == {
            "atlascloud",
            "comfyui_direct",
            "ollama",
            "poe",
            "runpod",
        }
        assert not _is_provider_submodule_loaded()

    def test_registry_has_does_not_load_submodules(self) -> None:
        assert not _is_provider_submodule_loaded()
        from app.services.providers import registry
        assert registry.has("poe") is True
        assert not _is_provider_submodule_loaded()

    def test_registry_get_loads_submodule_on_demand(self) -> None:
        assert not _is_provider_submodule_loaded()
        from app.services.providers import registry
        cls = registry.get("poe")
        assert cls is not None
        assert "app.services.providers.poe" in sys.modules
        _unload_providers()

    def test_registry_create_loads_submodule_on_demand(self) -> None:
        assert not _is_provider_submodule_loaded()
        from app.services.providers import registry

        class _FakeProvider:
            def __init__(self, provider_id: Any, config: dict[str, Any]) -> None:
                pass

            async def initialize(self, config: dict[str, Any]) -> None:
                pass

        registry.register("fake_lazy", cast(Any, _FakeProvider))
        import asyncio

        instance = asyncio.run(registry.create("fake_lazy", uuid4(), {}))
        assert instance is not None

    def test_broken_provider_import_is_isolated(self) -> None:
        _unload_providers()

        import app.services.providers as providers

        providers.registry.register(
            "broken",
            "app.services.providers.definitely_missing:MissingProvider",
        )

        assert providers.registry.get("poe") is not None
        with pytest.raises(ValueError, match="provider unavailable"):
            providers.registry.get("broken")

    def test_registry_get_wraps_import_error(self) -> None:
        from app.services.providers.registry import ProviderRegistry

        reg = ProviderRegistry()
        reg.register("broken", "app.services.providers.nonexistent:FakeClass")
        with pytest.raises(ValueError, match="provider unavailable"):
            reg.get("broken")
