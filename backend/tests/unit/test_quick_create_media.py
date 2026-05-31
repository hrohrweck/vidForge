"""Unit tests for the quick media generation endpoint and Celery task.

Covers:
- POST /api/media/generate endpoint (auth, validation, dispatch)
- generate_quick_media task retry classification
- _generate_quick_media retry behaviour (mocked inner dependencies)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.api.media import QuickGenerateRequest, QuickGenerateResponse


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class FakeCeleryTask:
    """A mock Celery task that records ``.delay()`` calls and returns a
    predictable task id."""

    calls: list[tuple[tuple, dict]]

    def __init__(self) -> None:
        self.calls = []
        self._task_id = "fake-task-" + str(uuid4())[:8]

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = MagicMock()
        result.id = self._task_id
        return result


def _patch_fake_task(monkeypatch, fake_task: FakeCeleryTask) -> None:
    """Replace ``generate_quick_media`` at its definition site so the
    lazy ``from app.workers.tasks import generate_quick_media`` inside
    the endpoint picks up the fake."""
    monkeypatch.setattr("app.workers.tasks.generate_quick_media", fake_task)


# ---------------------------------------------------------------------------
# Endpoint tests (POST /api/media/generate)
# ---------------------------------------------------------------------------


class TestQuickGenerateEndpoint:
    """Tests for the HTTP endpoint itself."""

    # ── 1. Happy path ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_endpoint_returns_202(
        self,
        client: AsyncClient,
        regular_user_token: str,
        monkeypatch,
    ):
        """POST /api/media/generate with valid body → 202 + task_id."""
        fake_task = FakeCeleryTask()
        _patch_fake_task(monkeypatch, fake_task)

        response = await client.post(
            "/api/media/generate",
            json={
                "model_id": "model-abc",
                "prompt": "a test prompt",
                "aspect_ratio": "16:9",
                "duration": 5,
            },
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["task_id"] == fake_task._task_id
        assert body["status"] == "queued"

    # ── 2. Auth ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_endpoint_requires_auth(self, client: AsyncClient):
        """No Authorization header → 401."""
        response = await client.post(
            "/api/media/generate",
            json={"model_id": "model-abc", "prompt": "test"},
        )
        assert response.status_code == 401

    # ── 3. Validation ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_endpoint_missing_model(
        self,
        client: AsyncClient,
        regular_user_token: str,
    ):
        """Missing required field ``model_id`` → 422."""
        response = await client.post(
            "/api/media/generate",
            json={"prompt": "test prompt"},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_missing_prompt(
        self,
        client: AsyncClient,
        regular_user_token: str,
    ):
        """Missing required field ``prompt`` → 422."""
        response = await client.post(
            "/api/media/generate",
            json={"model_id": "model-abc"},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 422

    # ── 5. Celery dispatch ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_task_dispatches_celery(
        self,
        client: AsyncClient,
        regular_user_token: str,
        monkeypatch,
    ):
        """``generate_quick_media.delay()`` is called with correct args."""
        fake_task = FakeCeleryTask()
        _patch_fake_task(monkeypatch, fake_task)

        response = await client.post(
            "/api/media/generate",
            json={
                "model_id": "flux-schnell",
                "prompt": "golden retriever",
                "aspect_ratio": "1:1",
                "duration": 3,
                "negative_prompt": "blurry",
                "seed": 42,
            },
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )

        assert response.status_code == 202
        assert len(fake_task.calls) == 1
        _, kwargs = fake_task.calls[0]
        assert kwargs["model_id"] == "flux-schnell"
        assert kwargs["prompt"] == "golden retriever"
        assert kwargs["aspect_ratio"] == "1:1"
        assert kwargs["duration"] == 3
        assert kwargs["negative_prompt"] == "blurry"
        assert kwargs["seed"] == 42
        assert kwargs["user_id"]  # uuid string, always present

    @pytest.mark.asyncio
    async def test_default_values_passed_to_task(
        self,
        client: AsyncClient,
        regular_user_token: str,
        monkeypatch,
    ):
        """Optional fields default correctly when omitted from request."""
        fake_task = FakeCeleryTask()
        _patch_fake_task(monkeypatch, fake_task)

        await client.post(
            "/api/media/generate",
            json={"model_id": "m", "prompt": "p"},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )

        _, kwargs = fake_task.calls[0]
        assert kwargs["aspect_ratio"] == "1:1"
        assert kwargs["duration"] == 5
        assert kwargs["negative_prompt"] is None
        assert kwargs["seed"] is None


# ---------------------------------------------------------------------------
# Recoverable-error classification (unit tests on _is_quick_recoverable)
# ---------------------------------------------------------------------------


class TestRecoverableClassification:
    """Tests for :func:`app.workers.tasks._is_quick_recoverable`."""

    @staticmethod
    def _make_exc(msg: str) -> Exception:
        return RuntimeError(msg)

    # ── 6. Recoverable errors ──────────────────────────────────────

    @pytest.mark.parametrize(
        "message",
        [
            "rate limit exceeded",
            "RATE LIMIT reached",
            "Queue is full, try again later",
            "HTTP 429: Too Many Requests",
            "server 502 Bad Gateway",
            "HTTP 503 Service Unavailable",
            "504 Gateway Timeout",
            "connection timed out",
            "temporary server error, retry",
            "Overloaded, please wait",
            "capacity exceeded",
            "Too Many Requests",
        ],
    )
    def test_recoverable_messages(self, message: str):
        """Recoverable markers cause ``_is_quick_recoverable`` to be True."""
        from app.workers.tasks import _is_quick_recoverable

        assert _is_quick_recoverable(self._make_exc(message)) is True

    # ── 7. Non-recoverable errors ──────────────────────────────────

    @pytest.mark.parametrize(
        "message",
        [
            "invalid prompt: contains banned words",
            "authentication failed",
            "model not found: unknown-model",
            "file not found at path",
            "invalid aspect ratio '42:0'",
            "bad request",
        ],
    )
    def test_non_recoverable_messages(self, message: str):
        """Non-recoverable messages cause ``_is_quick_recoverable`` to be False."""
        from app.workers.tasks import _is_quick_recoverable

        assert _is_quick_recoverable(self._make_exc(message)) is False

    def test_case_insensitive(self):
        """Marker matching is case-insensitive."""
        from app.workers.tasks import _is_quick_recoverable

        assert _is_quick_recoverable(self._make_exc("RATE LIMIT")) is True
        assert _is_quick_recoverable(self._make_exc("TIMEOUT")) is True


# ---------------------------------------------------------------------------
# Retry-behaviour tests on _generate_quick_media
# ---------------------------------------------------------------------------


class TestGenerateQuickMediaRetry:
    """Verify that ``_generate_quick_media`` calls ``self.retry()`` when
    appropriate (or raises immediately otherwise)."""

    # ── helpers ────────────────────────────────────────────────────

    def _mock_task_self(self, retries: int = 0, max_retries: int = 4):
        """Build a mock Celery task ``self`` object."""
        task_self = MagicMock()
        task_self.request.retries = retries
        task_self.max_retries = max_retries
        # Celery self.retry raises Retry; simulate that.
        task_self.retry.side_effect = RuntimeError("celery-retry")
        return task_self

    def _mock_ctx_and_db(self):
        """Mock WorkerContext and DB session via patch."""
        mock_session = AsyncMock()
        # --- model config lookup ---
        config = MagicMock()
        config.model_id = "model-abc"
        config.modality = "image"
        config.provider_id = uuid4()
        config.is_active = True
        # --- provider lookup ---
        provider = MagicMock()
        provider.id = config.provider_id
        provider.is_active = True

        # scalars().first() for ModelConfig
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = config
        # scalars().one_or_none() for Provider
        scalars_provider = MagicMock()
        scalars_provider.scalar_one_or_none.return_value = provider

        # execute returns different results on successive calls
        execute_side_effect = [
            MagicMock(scalars=MagicMock(return_value=scalars_mock)),
            MagicMock(scalars=MagicMock(return_value=scalars_provider)),
        ]
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        # ctx manager setup
        ctx_manager = MagicMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_manager.__aexit__ = AsyncMock(return_value=None)

        factory = MagicMock(return_value=ctx_manager)

        ctx_mock = MagicMock()
        ctx_mock.session_factory = factory

        return ctx_mock, mock_session

    # ── 6. Retry on recoverable ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_retry_on_recoverable_error(self):
        """Task calls ``self.retry()`` when ``generate_image`` raises a
        recoverable error with retries remaining."""
        ctx_mock, mock_session = self._mock_ctx_and_db()
        task_self = self._mock_task_self(retries=0)

        from app.workers.tasks import _generate_quick_media

        with patch(
            "app.services.media_generator.generate_image",
            side_effect=RuntimeError("rate limit exceeded"),
        ), patch("app.workers.tasks.ctx", ctx_mock):
            with pytest.raises(RuntimeError, match="celery-retry"):
                await _generate_quick_media(
                    self=task_self,
                    user_id=str(uuid4()),
                    model_id="model-abc",
                    prompt="test",
                    aspect_ratio="1:1",
                    duration=5,
                    negative_prompt=None,
                    seed=None,
                )

        task_self.retry.assert_called_once()

    # ── 7. No retry on non-recoverable ──────────────────────────────

    @pytest.mark.asyncio
    async def test_fail_on_non_recoverable(self):
        """Task does **not** call ``self.retry()`` on non-recoverable errors."""
        ctx_mock, mock_session = self._mock_ctx_and_db()
        task_self = self._mock_task_self(retries=0)

        from app.workers.tasks import _generate_quick_media

        # Use a non-recoverable message: "invalid prompt"
        with patch(
            "app.services.media_generator.generate_image",
            side_effect=RuntimeError("invalid prompt: bad"),
        ), patch("app.workers.tasks.ctx", ctx_mock):
            with pytest.raises(RuntimeError, match="invalid prompt: bad"):
                await _generate_quick_media(
                    self=task_self,
                    user_id=str(uuid4()),
                    model_id="model-abc",
                    prompt="test",
                    aspect_ratio="1:1",
                    duration=5,
                    negative_prompt=None,
                    seed=None,
                )

        task_self.retry.assert_not_called()

    # ── Edge: retries exhausted ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_retry_when_retries_exhausted(self):
        """Task does **not** call ``self.retry()`` when retries are exhausted,
        even for recoverable errors."""
        ctx_mock, mock_session = self._mock_ctx_and_db()
        # retries == max_retries means no more retries
        task_self = self._mock_task_self(retries=4, max_retries=4)

        from app.workers.tasks import _generate_quick_media

        with patch(
            "app.services.media_generator.generate_image",
            side_effect=RuntimeError("rate limit exceeded"),
        ), patch("app.workers.tasks.ctx", ctx_mock):
            with pytest.raises(RuntimeError, match="rate limit exceeded"):
                await _generate_quick_media(
                    self=task_self,
                    user_id=str(uuid4()),
                    model_id="model-abc",
                    prompt="test",
                    aspect_ratio="1:1",
                    duration=5,
                    negative_prompt=None,
                    seed=None,
                )

        task_self.retry.assert_not_called()
