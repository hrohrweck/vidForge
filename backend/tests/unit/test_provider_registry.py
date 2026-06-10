from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.providers import (
    AtlasCloudProvider,
    ComfyUIDirectProvider,
    OllamaProvider,
    PoeProvider,
    ProviderRegistry,
    RunPodProvider,
    registry,
)
from app.services.providers.base import ComfyUIProvider, ProviderInfo


class _RecordingProvider(ComfyUIProvider):
    """Minimal ComfyUIProvider used to verify registry behavior.

    Tracks constructor + initialize calls so tests can assert on the
    `create()` contract without spinning up real provider state.
    """

    instances: list["_RecordingProvider"] = []
    initialize_calls: list[dict[str, Any]] = []

    def __init__(self, provider_id: Any, config: dict[str, Any]) -> None:
        self.provider_id = provider_id
        self.config = config
        self.initialized_with: dict[str, Any] | None = None
        _RecordingProvider.instances.append(self)

    async def initialize(self, config: dict[str, Any]) -> None:
        self.initialized_with = config
        _RecordingProvider.initialize_calls.append(config)

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        return "test-prompt-id"

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 172800.0,
        progress_callback: Any = None,
    ) -> dict:
        return {"completed": True}

    async def get_output(self, result: dict) -> bytes | None:
        return b""

    async def cancel_job(self, job_id: str) -> bool:
        return True

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(
            name="recording",
            provider_type="recording",
            is_available=True,
        )

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 1.0

    async def shutdown(self) -> None:
        return None


@pytest.fixture
def fresh_registry() -> ProviderRegistry:
    return ProviderRegistry()


@pytest.fixture(autouse=True)
def _reset_recording_provider_state() -> None:
    _RecordingProvider.instances.clear()
    _RecordingProvider.initialize_calls.clear()


def test_register_and_get_returns_class(fresh_registry: ProviderRegistry) -> None:
    fresh_registry.register("recording", _RecordingProvider)
    assert fresh_registry.get("recording") is _RecordingProvider


def test_get_unknown_type_raises_value_error(
    fresh_registry: ProviderRegistry,
) -> None:
    with pytest.raises(ValueError, match="Unknown provider type: nope"):
        fresh_registry.get("nope")


def test_register_rejects_empty_type(fresh_registry: ProviderRegistry) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        fresh_registry.register("", _RecordingProvider)


def test_register_rejects_non_string_type(
    fresh_registry: ProviderRegistry,
) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        fresh_registry.register(123, _RecordingProvider)  # type: ignore[arg-type]


def test_register_overwrites_existing(fresh_registry: ProviderRegistry) -> None:
    sentinel = MagicMock()
    fresh_registry.register("recording", _RecordingProvider)
    fresh_registry.register("recording", sentinel)
    assert fresh_registry.get("recording") is sentinel


def test_has_returns_true_for_registered(
    fresh_registry: ProviderRegistry,
) -> None:
    fresh_registry.register("recording", _RecordingProvider)
    assert fresh_registry.has("recording") is True


def test_has_returns_false_for_unknown(
    fresh_registry: ProviderRegistry,
) -> None:
    assert fresh_registry.has("nope") is False


def test_list_types_is_sorted(fresh_registry: ProviderRegistry) -> None:
    fresh_registry.register("zeta", _RecordingProvider)
    fresh_registry.register("alpha", _RecordingProvider)
    fresh_registry.register("mu", _RecordingProvider)
    assert fresh_registry.list_types() == ["alpha", "mu", "zeta"]


def test_list_types_empty_when_no_providers(
    fresh_registry: ProviderRegistry,
) -> None:
    assert fresh_registry.list_types() == []


async def test_create_instantiates_and_initializes(
    fresh_registry: ProviderRegistry,
) -> None:
    fresh_registry.register("recording", _RecordingProvider)
    provider_id = uuid4()
    config = {"api_key": "secret"}

    instance = await fresh_registry.create("recording", provider_id, config)

    assert isinstance(instance, _RecordingProvider)
    assert instance.provider_id == provider_id
    assert instance.config == config
    assert instance.initialized_with == config
    assert _RecordingProvider.initialize_calls == [config]


async def test_create_propagates_initialize_errors(
    fresh_registry: ProviderRegistry,
) -> None:
    class _BrokenProvider(_RecordingProvider):
        async def initialize(self, config: dict[str, Any]) -> None:
            raise RuntimeError("boom")

    fresh_registry.register("broken", _BrokenProvider)

    with pytest.raises(RuntimeError, match="boom"):
        await fresh_registry.create("broken", uuid4(), {})


async def test_create_for_unknown_type_raises_value_error(
    fresh_registry: ProviderRegistry,
) -> None:
    with pytest.raises(ValueError, match="Unknown provider type: missing"):
        await fresh_registry.create("missing", uuid4(), {})


def test_default_registry_has_all_five_provider_types() -> None:
    assert set(registry.list_types()) == {
        "atlascloud",
        "comfyui_direct",
        "ollama",
        "poe",
        "runpod",
    }


@pytest.mark.parametrize(
    "provider_type,expected_class",
    [
        ("atlascloud", AtlasCloudProvider),
        ("comfyui_direct", ComfyUIDirectProvider),
        ("ollama", OllamaProvider),
        ("poe", PoeProvider),
        ("runpod", RunPodProvider),
    ],
)
def test_default_registry_maps_type_to_correct_class(
    provider_type: str, expected_class: type[ComfyUIProvider]
) -> None:
    assert registry.get(provider_type).__name__ == expected_class.__name__


@pytest.mark.parametrize("provider_type", ["atlascloud", "comfyui_direct", "ollama", "poe", "runpod"])
def test_default_registry_has_each_provider(provider_type: str) -> None:
    assert registry.has(provider_type) is True


async def test_create_with_mock_provider_via_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    init_mock = AsyncMock()
    fake_instance = MagicMock()
    fake_instance.initialize = init_mock
    fake_class = MagicMock(return_value=fake_instance)
    fake_class.__name__ = "FakeProvider"

    fresh_registry = ProviderRegistry()
    fresh_registry.register("fake", fake_class)

    provider_id = uuid4()
    config = {"x": 1}
    result = await fresh_registry.create("fake", provider_id, config)

    fake_class.assert_called_once_with(provider_id, config)
    init_mock.assert_awaited_once_with(config)
    assert result is fake_instance
