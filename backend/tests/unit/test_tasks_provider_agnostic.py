"""Verify tasks.py is provider-agnostic: no provider-type-specific branching.

Tests cover:
- ProviderSemaphore (generalized from ComfyUISemaphore)
- _discover_models_via_registry (registry-based model sync)
- Source-level verification (no provider-specific imports/patterns)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.providers.base import (
    ComfyUIProvider,
    ProviderCapabilities,
    ProviderInfo,
)

# ---------------------------------------------------------------------------
# ProviderSemaphore tests
# ---------------------------------------------------------------------------


class TestProviderSemaphore:

    @pytest.mark.asyncio
    async def test_acquire_when_under_limit(self, mocker):
        from app.workers import tasks as tmod

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=0)
        mock_redis.incr = AsyncMock()

        # Set private attr — redis is a read-only @property
        tmod.ctx._redis = mock_redis

        sem = tmod.ProviderSemaphore(key="test:key", max_concurrent=2)
        acquired = await sem.acquire("job-1")
        assert acquired is True
        mock_redis.incr.assert_called_once_with("test:key")

    @pytest.mark.asyncio
    async def test_acquire_when_at_limit(self, mocker):
        from app.workers import tasks as tmod

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=2)
        mock_redis.incr = AsyncMock()

        tmod.ctx._redis = mock_redis

        sem = tmod.ProviderSemaphore(key="test:key", max_concurrent=2)
        acquired = await sem.acquire("job-1")
        assert acquired is False
        mock_redis.incr.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_when_acquired(self, mocker):
        from app.workers import tasks as tmod

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=2)
        mock_redis.decr = AsyncMock()

        tmod.ctx._redis = mock_redis

        sem = tmod.ProviderSemaphore(key="test:key", max_concurrent=2)
        sem._acquired = True
        await sem.release()
        mock_redis.decr.assert_called_once_with("test:key")

    @pytest.mark.asyncio
    async def test_release_when_not_acquired(self, mocker):
        from app.workers import tasks as tmod

        mock_redis = MagicMock()
        mock_redis.decr = AsyncMock()

        tmod.ctx._redis = mock_redis

        sem = tmod.ProviderSemaphore(key="test:key", max_concurrent=2)
        await sem.release()
        mock_redis.decr.assert_not_called()

    def test_key_is_configurable_per_provider(self):
        from app.workers.tasks import ProviderSemaphore

        sem_a = ProviderSemaphore(key="provider:processing:uuid-a", max_concurrent=3)
        sem_b = ProviderSemaphore(key="provider:processing:uuid-b", max_concurrent=1)

        assert sem_a._key == "provider:processing:uuid-a"
        assert sem_b._key == "provider:processing:uuid-b"
        assert sem_a._max == 3
        assert sem_b._max == 1


# ---------------------------------------------------------------------------
# _discover_models_via_registry tests
# ---------------------------------------------------------------------------


class _MockProviderForSync(ComfyUIProvider):
    """Configurable mock provider for sync testing."""

    def __init__(self, provider_id: Any, config: dict[str, Any]) -> None:
        self.provider_id = provider_id
        self.config = config
        self.initialized = False
        self._shutdown_called = False
        self._sync_result: list[dict[str, Any]] = []
        self._capabilities = ProviderCapabilities(
            supports_model_sync=True,
            supports_video=True,
        )
        self._sync_should_raise: Exception | None = None

    async def initialize(self, config: dict[str, Any]) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self._shutdown_called = True

    def get_capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def sync_models(self) -> list[dict[str, Any]]:
        if self._sync_should_raise:
            raise self._sync_should_raise
        return self._sync_result

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        return ""

    async def wait_for_completion(self, **kwargs: Any) -> dict:
        return {}

    async def get_output(self, result: dict) -> bytes | None:
        return None

    async def cancel_job(self, job_id: str) -> bool:
        return True

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(name="mock", provider_type="mock", is_available=True)

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 1.0


class TestDiscoverModelsViaRegistry:

    @pytest.fixture
    def mock_provider_record(self):
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Provider"
        p.provider_type = "mock_type"
        p.config = {"api_key": "test"}
        return p

    @pytest.mark.asyncio
    async def test_uses_registry_create(self, mocker, mock_provider_record):
        from app.workers.tasks import _discover_models_via_registry

        mock_instance = _MockProviderForSync(uuid4(), {})
        mock_instance._sync_result = [{"model_id": "test-model"}]

        mock_create = AsyncMock(return_value=mock_instance)
        mocker.patch("app.services.providers.registry.create", mock_create)

        result = await _discover_models_via_registry(mock_provider_record)

        mock_create.assert_called_once_with(
            mock_provider_record.provider_type,
            mock_provider_record.id,
            mock_provider_record.config,
        )
        assert len(result) == 1
        assert result[0]["model_id"] == "test-model"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sync_support(self, mocker, mock_provider_record):
        from app.workers.tasks import _discover_models_via_registry

        mock_instance = _MockProviderForSync(uuid4(), {})
        mock_instance._capabilities = ProviderCapabilities(
            supports_model_sync=False, supports_video=True
        )

        mock_create = AsyncMock(return_value=mock_instance)
        mocker.patch("app.services.providers.registry.create", mock_create)

        result = await _discover_models_via_registry(mock_provider_record)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_not_implemented(self, mocker, mock_provider_record):
        from app.workers.tasks import _discover_models_via_registry

        mock_instance = _MockProviderForSync(uuid4(), {})
        mock_instance._sync_should_raise = NotImplementedError("nope")

        mock_create = AsyncMock(return_value=mock_instance)
        mocker.patch("app.services.providers.registry.create", mock_create)

        result = await _discover_models_via_registry(mock_provider_record)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self, mocker, mock_provider_record):
        from app.workers.tasks import _discover_models_via_registry

        mock_instance = _MockProviderForSync(uuid4(), {})
        mock_instance._sync_should_raise = RuntimeError("boom")

        mock_create = AsyncMock(return_value=mock_instance)
        mocker.patch("app.services.providers.registry.create", mock_create)

        result = await _discover_models_via_registry(mock_provider_record)
        assert result == []

    @pytest.mark.asyncio
    async def test_shuts_down_provider_in_finally(self, mocker, mock_provider_record):
        from app.workers.tasks import _discover_models_via_registry

        mock_instance = _MockProviderForSync(uuid4(), {})
        mock_instance._sync_should_raise = RuntimeError("boom")

        mock_create = AsyncMock(return_value=mock_instance)
        mocker.patch("app.services.providers.registry.create", mock_create)

        await _discover_models_via_registry(mock_provider_record)
        assert mock_instance._shutdown_called is True

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_discovered_models(self, mocker, mock_provider_record):
        from app.workers.tasks import _discover_models_via_registry

        mock_instance = _MockProviderForSync(uuid4(), {})
        mock_instance._sync_result = []

        mock_create = AsyncMock(return_value=mock_instance)
        mocker.patch("app.services.providers.registry.create", mock_create)

        result = await _discover_models_via_registry(mock_provider_record)
        assert result == []


# ---------------------------------------------------------------------------
# Source-level verification (grep-based — no provider-specific patterns)
# ---------------------------------------------------------------------------

TASKS_PY = Path(__file__).resolve().parent.parent.parent / "app" / "workers" / "tasks.py"


def _read_tasks() -> str:
    return TASKS_PY.read_text()


class TestNoProviderSpecificReferences:

    def test_no_specific_provider_imports(self):
        content = _read_tasks()
        assert "PoeProvider" not in content
        assert "AtlasCloudProvider" not in content
        assert "ComfyUIDirectProvider" not in content
        assert "RunPodProvider" not in content

    def test_no_deprecated_function_names(self):
        content = _read_tasks()
        assert "_run_poe_job" not in content
        assert "_run_runpod_job" not in content
        assert "_sync_atlascloud_models" not in content
        assert "_sync_poe_models" not in content

    def test_no_python_runtime_provider_type_checks(self):
        content = _read_tasks()
        forbidden_runtime = [
            'provider_record.provider_type == "comfyui_direct"',
            "provider_record.provider_type == 'comfyui_direct'",
            'provider_record.provider_type == "poe"',
            "provider_record.provider_type == 'poe'",
            'provider_record.provider_type == "runpod"',
            "provider_record.provider_type == 'runpod'",
            'provider_record.provider_type == "atlascloud"',
            "provider_record.provider_type == 'atlascloud'",
        ]
        for pattern in forbidden_runtime:
            assert pattern not in content, f"Runtime check found: {pattern}"

    def test_comfyui_semaphore_renamed(self):
        content = _read_tasks()
        assert "ComfyUISemaphore" not in content
        assert "ProviderSemaphore" in content

    def test_imports_registry(self):
        content = _read_tasks()
        assert "from app.services.providers" in content

    def test_no_runpod_specific_budget_check(self):
        content = _read_tasks()
        assert 'provider.provider_type == "runpod"' not in content
        assert "provider.provider_type == 'runpod'" not in content

    def test_no_poe_model_import(self):
        content = _read_tasks()
        assert "from app.database import PoeModel" not in content
