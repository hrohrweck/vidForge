"""Integration tests for the quick media generation endpoint.

Requires: PostgreSQL at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/ -v
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class FakeCeleryTask:
    """Records ``.delay()`` calls, returns a predictable task id."""

    calls: list[tuple[tuple, dict]]

    def __init__(self) -> None:
        self.calls = []
        self._task_id = "fake-int-" + str(uuid4())[:8]

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = MagicMock()
        result.id = self._task_id
        return result


@pytest.fixture
def fake_task():
    return FakeCeleryTask()


@pytest.fixture
def patched_endpoint(monkeypatch, fake_task: FakeCeleryTask):
    """Replace the Celery task so no Redis connection is needed."""
    monkeypatch.setattr("app.workers.tasks.generate_quick_media", fake_task)
    return fake_task


class TestQuickGenerateIntegration:
    """End-to-end tests for POST /api/media/media/generate."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.post(
            "/api/media/media/generate",
            json={"model_id": "any-model", "prompt": "a prompt"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_model_returns_422(
        self, authenticated_client: AsyncClient, patched_endpoint
    ):
        response = await authenticated_client.post(
            "/api/media/media/generate",
            json={"prompt": "only prompt, no model"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_prompt_returns_422(
        self, authenticated_client: AsyncClient, patched_endpoint
    ):
        response = await authenticated_client.post(
            "/api/media/media/generate",
            json={"model_id": "some-model"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_request_returns_202(
        self, authenticated_client: AsyncClient, patched_endpoint: FakeCeleryTask
    ):
        response = await authenticated_client.post(
            "/api/media/media/generate",
            json={
                "model_id": "test-model",
                "prompt": "integration test prompt",
                "aspect_ratio": "16:9",
                "duration": 5,
            },
        )
        assert response.status_code == 202
        body = response.json()
        assert body["task_id"] == patched_endpoint._task_id
        assert body["status"] == "queued"

    @pytest.mark.asyncio
    async def test_default_values_accepted(
        self, authenticated_client: AsyncClient, patched_endpoint
    ):
        response = await authenticated_client.post(
            "/api/media/media/generate",
            json={"model_id": "any-model", "prompt": "minimal"},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["task_id"]
        assert body["status"] == "queued"

    @pytest.mark.asyncio
    async def test_dispatch_args(
        self, authenticated_client: AsyncClient, patched_endpoint: FakeCeleryTask
    ):
        """Verify the Celery task is dispatched with correct arguments."""
        await authenticated_client.post(
            "/api/media/media/generate",
            json={
                "model_id": "my-model",
                "prompt": "dispatch test",
                "aspect_ratio": "9:16",
                "duration": 7,
                "negative_prompt": "nope",
                "seed": 999,
            },
        )
        assert len(patched_endpoint.calls) == 1
        _, kwargs = patched_endpoint.calls[0]
        assert kwargs["model_id"] == "my-model"
        assert kwargs["prompt"] == "dispatch test"
        assert kwargs["aspect_ratio"] == "9:16"
        assert kwargs["duration"] == 7
        assert kwargs["negative_prompt"] == "nope"
        assert kwargs["seed"] == 999
