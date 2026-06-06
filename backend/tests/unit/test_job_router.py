"""Tests for the refactored job_router.py.

Verifies:
- Zero provider class leakage (no hardcoded provider imports)
- Registry-based provider instantiation
- Capability-based provider selection
- Generalized budget checking (all providers with cost > 0)
- Generalized spend recording in execute_job
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.job_router import JobRouter, JobRouterError
from app.services.providers.base import ProviderCapabilities


FORBIDDEN_PROVIDER_CLASSES = [
    "AtlasCloudProvider",
    "ComfyUIDirectProvider",
    "PoeProvider",
    "RunPodProvider",
    "OllamaProvider",
]


def _make_provider(
    provider_type: str = "test_provider",
    is_active: bool = True,
    priority: int = 0,
    config: dict[str, Any] | None = None,
    name: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name=name or f"{provider_type}-provider",
        provider_type=provider_type,
        is_active=is_active,
        priority=priority,
        config=config or {},
        daily_budget_limit=None,
        current_daily_spend=Decimal("0"),
    )


def _make_mock_instance(
    supports_image: bool = True,
    supports_video: bool = True,
    estimated_cost: float = 0.0,
) -> AsyncMock:
    instance = AsyncMock()
    instance.get_capabilities = MagicMock(
        return_value=ProviderCapabilities(
            supports_image=supports_image,
            supports_video=supports_video,
        )
    )
    instance.estimate_cost = AsyncMock(return_value=estimated_cost)
    instance.estimate_duration = AsyncMock(return_value=10.0)
    instance.queue_prompt = AsyncMock(return_value="run-123")
    instance.wait_for_completion = AsyncMock(return_value={"status": "done"})
    instance.get_status = AsyncMock()
    instance.cancel_job = AsyncMock(return_value=True)
    return instance


_SENTINEL = object()


def _make_job(provider_id=_SENTINEL) -> Any:
    pid = uuid4() if provider_id is _SENTINEL else provider_id
    return SimpleNamespace(
        id=uuid4(),
        provider_id=pid,
        started_at=None,
        completed_at=None,
        actual_cost=None,
    )


class _FakeResult:
    def __init__(self, scalars_list: list | None = None, scalar_one=None):
        self._scalars_list = scalars_list or []
        self._scalar_one = scalar_one

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalars(self):
        inner = MagicMock()
        inner.all.return_value = self._scalars_list
        return inner


class TestZeroProviderLeakage:
    def test_no_provider_class_imports(self):
        source = Path("app/services/job_router.py").read_text()
        for class_name in FORBIDDEN_PROVIDER_CLASSES:
            assert class_name not in source, (
                f"Provider class '{class_name}' found in job_router.py — "
                "should use registry instead"
            )

    def test_no_create_provider_instance_method(self):
        source = Path("app/services/job_router.py").read_text()
        assert "_create_provider_instance" not in source, (
            "_create_provider_instance still exists — should use registry.create()"
        )

    def test_no_provider_specific_routing(self):
        source = Path("app/services/job_router.py").read_text()
        provider_specific_patterns = [
            r'provider_type\s*==\s*"comfyui_direct"',
            r'provider_type\s*==\s*"runpod"',
            r'provider_type\s*==\s*"atlascloud"',
            r'provider_type\s*==\s*"poe"',
        ]
        for pattern in provider_specific_patterns:
            assert not re.search(pattern, source), (
                f"Provider-specific routing pattern found: {pattern}"
            )

    def test_uses_registry_import(self):
        source = Path("app/services/job_router.py").read_text()
        assert "from app.services.providers import registry" in source


class TestGetProviderInstance:
    @pytest.mark.asyncio
    async def test_uses_registry_create(self):
        provider = _make_provider("test_type")
        mock_instance = _make_mock_instance()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalar_one=provider))

        router = JobRouter(db)

        with patch(
            "app.services.job_router.registry.create",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ) as mock_create:
            result = await router.get_provider_instance(provider.id)

            mock_create.assert_awaited_once_with(
                provider.provider_type, provider.id, provider.config
            )
            assert result is mock_instance

    @pytest.mark.asyncio
    async def test_caches_provider_instance(self):
        provider = _make_provider()
        mock_instance = _make_mock_instance()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalar_one=provider))

        router = JobRouter(db)
        router._providers[provider.id] = mock_instance

        result = await router.get_provider_instance(provider.id)
        assert result is mock_instance
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_on_missing_provider(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalar_one=None))

        router = JobRouter(db)

        with pytest.raises(JobRouterError, match="not found"):
            await router.get_provider_instance(uuid4())


class TestSelectProvider:
    @pytest.mark.asyncio
    async def test_uuid_preference_selects_specific_provider(self):
        provider = _make_provider()
        mock_instance = _make_mock_instance()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalar_one=provider))

        router = JobRouter(db)

        with patch.object(router, "get_provider_instance", return_value=mock_instance):
            result_provider, result_instance, reason = await router.select_provider(
                preference=str(provider.id)
            )

            assert result_provider is provider
            assert result_instance is mock_instance
            assert "selected by ID" in reason

    @pytest.mark.asyncio
    async def test_type_preference_filters_by_type(self):
        provider = _make_provider("custom_type", priority=5)
        mock_instance = _make_mock_instance()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalars_list=[provider]))

        router = JobRouter(db)

        with patch.object(router, "get_provider_instance", return_value=mock_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 0, "online": 0, "busy": 0, "offline": 0},
            ):
                result_provider, _, _ = await router.select_provider(
                    preference="custom_type"
                )

                assert result_provider is provider

    @pytest.mark.asyncio
    async def test_auto_selects_highest_priority(self):
        low = _make_provider("type_a", priority=1, name="low")
        high = _make_provider("type_b", priority=10, name="high")
        mock_instance = _make_mock_instance()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalars_list=[high, low]))

        router = JobRouter(db)

        with patch.object(router, "get_provider_instance", return_value=mock_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 0, "online": 0, "busy": 0, "offline": 0},
            ):
                result_provider, _, _ = await router.select_provider()
                assert result_provider is high

    @pytest.mark.asyncio
    async def test_no_providers_raises(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalars_list=[]))

        router = JobRouter(db)

        with pytest.raises(JobRouterError, match="No providers configured"):
            await router.select_provider()

    @pytest.mark.asyncio
    async def test_modality_image_filters_capability(self):
        image_provider = _make_provider("img_type", priority=1, name="img")
        video_only_provider = _make_provider("vid_type", priority=10, name="vid")

        img_instance = _make_mock_instance(supports_image=True, supports_video=False)
        vid_instance = _make_mock_instance(supports_image=False, supports_video=True)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_FakeResult(scalars_list=[video_only_provider, image_provider])
        )

        router = JobRouter(db)

        async def mock_get_instance(pid):
            if pid == video_only_provider.id:
                return vid_instance
            return img_instance

        with patch.object(router, "get_provider_instance", side_effect=mock_get_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 0, "online": 0, "busy": 0, "offline": 0},
            ):
                result_provider, _, _ = await router.select_provider(modality="image")
                assert result_provider is image_provider

    @pytest.mark.asyncio
    async def test_modality_video_filters_capability(self):
        image_only = _make_provider("img_type", priority=10, name="img")
        video_provider = _make_provider("vid_type", priority=1, name="vid")

        img_instance = _make_mock_instance(supports_image=True, supports_video=False)
        vid_instance = _make_mock_instance(supports_image=True, supports_video=True)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_FakeResult(scalars_list=[image_only, video_provider])
        )

        router = JobRouter(db)

        async def mock_get_instance(pid):
            if pid == image_only.id:
                return img_instance
            return vid_instance

        with patch.object(router, "get_provider_instance", side_effect=mock_get_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 0, "online": 0, "busy": 0, "offline": 0},
            ):
                result_provider, _, _ = await router.select_provider(modality="video")
                assert result_provider is video_provider

    @pytest.mark.asyncio
    async def test_skips_provider_with_busy_workers(self):
        busy_provider = _make_provider("busy_type", priority=10, name="busy")
        free_provider = _make_provider("free_type", priority=1, name="free")
        mock_instance = _make_mock_instance()

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_FakeResult(scalars_list=[busy_provider, free_provider])
        )

        router = JobRouter(db)

        async def mock_worker_count(provider_id):
            if provider_id == busy_provider.id:
                return {"total": 2, "online": 0, "busy": 2, "offline": 0}
            return {"total": 1, "online": 1, "busy": 0, "offline": 0}

        with patch.object(router, "get_provider_instance", return_value=mock_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                side_effect=mock_worker_count,
            ):
                result_provider, _, _ = await router.select_provider()
                assert result_provider is free_provider

    @pytest.mark.asyncio
    async def test_cloud_provider_no_workers_is_available(self):
        cloud = _make_provider("cloud_type", priority=5, name="cloud")
        mock_instance = _make_mock_instance()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalars_list=[cloud]))

        router = JobRouter(db)

        with patch.object(router, "get_provider_instance", return_value=mock_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 0, "online": 0, "busy": 0, "offline": 0},
            ):
                result_provider, _, _ = await router.select_provider()
                assert result_provider is cloud

    @pytest.mark.asyncio
    async def test_budget_check_applies_to_all_costly_providers(self):
        cheap = _make_provider("cheap_type", priority=10, name="cheap")
        expensive = _make_provider("expensive_type", priority=5, name="expensive")

        cheap_instance = _make_mock_instance(estimated_cost=0.0)
        expensive_instance = _make_mock_instance(estimated_cost=5.0)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_FakeResult(scalars_list=[cheap, expensive])
        )

        router = JobRouter(db)

        async def mock_get_instance(pid):
            if pid == cheap.id:
                return cheap_instance
            return expensive_instance

        budget_calls = []

        async def mock_check_budget(provider_id, cost):
            budget_calls.append((provider_id, cost))
            return True, "OK"

        with patch.object(router, "get_provider_instance", side_effect=mock_get_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 0, "online": 0, "busy": 0, "offline": 0},
            ):
                with patch.object(
                    router.budget_tracker,
                    "check_budget",
                    new_callable=AsyncMock,
                    side_effect=mock_check_budget,
                ):
                    result_provider, _, _ = await router.select_provider()

                    assert result_provider is cheap
                    assert len(budget_calls) == 0

                    budget_calls.clear()
                    db.execute = AsyncMock(
                        return_value=_FakeResult(scalars_list=[expensive])
                    )
                    result_provider, _, _ = await router.select_provider()
                    assert result_provider is expensive
                    assert len(budget_calls) == 1
                    assert budget_calls[0][0] == expensive.id

    @pytest.mark.asyncio
    async def test_skips_over_budget_provider(self):
        over_budget = _make_provider("over_type", priority=10, name="over")
        within_budget = _make_provider("within_type", priority=1, name="within")

        over_instance = _make_mock_instance(estimated_cost=10.0)
        within_instance = _make_mock_instance(estimated_cost=1.0)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_FakeResult(scalars_list=[over_budget, within_budget])
        )

        router = JobRouter(db)

        async def mock_get_instance(pid):
            if pid == over_budget.id:
                return over_instance
            return within_instance

        async def mock_check_budget(provider_id, cost):
            if provider_id == over_budget.id:
                return False, "Daily budget exceeded"
            return True, "Within budget"

        with patch.object(router, "get_provider_instance", side_effect=mock_get_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 0, "online": 0, "busy": 0, "offline": 0},
            ):
                with patch.object(
                    router.budget_tracker,
                    "check_budget",
                    new_callable=AsyncMock,
                    side_effect=mock_check_budget,
                ):
                    result_provider, _, _ = await router.select_provider()
                    assert result_provider is within_budget

    @pytest.mark.asyncio
    async def test_all_unavailable_raises(self):
        provider = _make_provider(priority=5)
        mock_instance = _make_mock_instance(estimated_cost=5.0)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult(scalars_list=[provider]))

        router = JobRouter(db)

        with patch.object(router, "get_provider_instance", return_value=mock_instance):
            with patch.object(
                router.worker_registry,
                "get_worker_count",
                new_callable=AsyncMock,
                return_value={"total": 2, "online": 0, "busy": 2, "offline": 0},
            ):
                with pytest.raises(JobRouterError, match="No available providers"):
                    await router.select_provider()


class TestExecuteJob:
    @pytest.mark.asyncio
    async def test_records_spend_for_costly_provider(self):
        provider = _make_provider("cloud_type", config={"gpu_type": "A100"})
        job = _make_job(provider.id)
        mock_instance = _make_mock_instance(estimated_cost=2.5)
        workflow = {"test": True}

        db = AsyncMock()

        router = JobRouter(db)

        with patch.object(
            router, "get_provider_record", return_value=provider
        ):
            with patch.object(
                router, "get_provider_instance", return_value=mock_instance
            ):
                with patch.object(
                    router.budget_tracker,
                    "record_spend",
                    new_callable=AsyncMock,
                ) as mock_record:
                    await router.execute_job(job, workflow)

                    mock_record.assert_awaited_once()
                    call_args = mock_record.call_args
                    assert call_args.args[0] == provider.id
                    assert call_args.args[1] == job.id
                    assert call_args.args[2] == Decimal("2.5")
                    assert call_args.kwargs["gpu_type"] == "A100"

        assert job.actual_cost == Decimal("2.5")

    @pytest.mark.asyncio
    async def test_skips_spend_for_free_provider(self):
        provider = _make_provider("local_type")
        job = _make_job(provider.id)
        mock_instance = _make_mock_instance(estimated_cost=0.0)
        workflow = {"test": True}

        db = AsyncMock()

        router = JobRouter(db)

        with patch.object(
            router, "get_provider_record", return_value=provider
        ):
            with patch.object(
                router, "get_provider_instance", return_value=mock_instance
            ):
                with patch.object(
                    router.budget_tracker,
                    "record_spend",
                    new_callable=AsyncMock,
                ) as mock_record:
                    await router.execute_job(job, workflow)
                    mock_record.assert_not_awaited()

        assert job.actual_cost is None

    @pytest.mark.asyncio
    async def test_no_provider_assigned_raises(self):
        job = _make_job(provider_id=None)
        db = AsyncMock()
        router = JobRouter(db)

        with pytest.raises(JobRouterError, match="no provider assigned"):
            await router.execute_job(job, {})

    @pytest.mark.asyncio
    async def test_records_spend_for_any_provider_type(self):
        for ptype in ["comfyui_direct", "runpod", "atlascloud", "poe", "custom"]:
            provider = _make_provider(ptype, config={})
            job = _make_job(provider.id)
            mock_instance = _make_mock_instance(estimated_cost=1.0)

            db = AsyncMock()
            router = JobRouter(db)

            with patch.object(
                router, "get_provider_record", return_value=provider
            ):
                with patch.object(
                    router, "get_provider_instance", return_value=mock_instance
                ):
                    with patch.object(
                        router.budget_tracker,
                        "record_spend",
                        new_callable=AsyncMock,
                    ) as mock_record:
                        await router.execute_job(job, {"test": True})
                        mock_record.assert_awaited_once(), (
                            f"record_spend not called for provider type '{ptype}'"
                        )
