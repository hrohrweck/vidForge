"""Unit tests for the Ollama provider, its model-sync integration,
and the provider-creation Alembic migration.

Covers:
- OllamaProvider initialization with config
- get_status returns correct ProviderInfo
- estimate_cost always returns 0.0
- queue_prompt / image-video ops raise NotImplementedError
- _sync_ollama_models delegates to ModelManager.list_available_models
- Migration creates the ollama provider row and cleans stale model_configs
- LLMProvider contract (chat, chat_stream, get_capabilities, classify_error,
  sync_models, list_models, supports_tools)
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from app.services.llm_service import LLMChunk, LLMError
from app.services.providers.base import (
    ImageProvider,
    LLMProvider,
    ProviderCapabilities,
    ProviderConnectionError,
    ProviderError,
    ProviderInfo,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    VideoProvider,
)
from app.services.providers.ollama import OllamaProvider

# ======================================================================
# Helpers
# ======================================================================


def _make_ollama_provider(
    provider_id: UUID | None = None,
    config: dict | None = None,
) -> OllamaProvider:
    return OllamaProvider(
        provider_id=provider_id or uuid4(),
        config=config or {},
    )


# ======================================================================
# 1. Initialization
# ======================================================================


class TestOllamaProviderInit:

    def test_initializes_with_provider_id(self):
        pid = uuid4()
        provider = OllamaProvider(provider_id=pid, config={})
        assert provider.provider_id == pid

    def test_stores_config_dict(self):
        cfg = {"foo": "bar"}
        provider = OllamaProvider(provider_id=uuid4(), config=cfg)
        assert provider.config == cfg

    def test_defaults_base_url_when_missing_in_config(self):
        provider = OllamaProvider(provider_id=uuid4(), config={})
        assert provider.base_url == "http://ollama:11434"

    def test_uses_custom_base_url_from_config(self):
        provider = OllamaProvider(
            provider_id=uuid4(),
            config={"base_url": "http://custom-ollama:9999"},
        )
        assert provider.base_url == "http://custom-ollama:9999"


# ======================================================================
# 2. get_status
# ======================================================================


class TestOllamaProviderGetStatus:

    @pytest.mark.asyncio
    async def test_returns_provider_info(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert isinstance(info, ProviderInfo)

    @pytest.mark.asyncio
    async def test_provider_type_is_ollama(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.provider_type == "ollama"

    @pytest.mark.asyncio
    async def test_name_is_ollama(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.name == "Ollama"

    @pytest.mark.asyncio
    async def test_is_available_is_true(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.is_available is True

    @pytest.mark.asyncio
    async def test_cost_per_job_is_zero(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.cost_per_job == 0.0


# ======================================================================
# 3. estimate_cost
# ======================================================================


class TestOllamaProviderEstimateCost:

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_workflow(self):
        provider = _make_ollama_provider()
        cost = await provider.estimate_cost({})
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_zero_for_non_empty_workflow(self):
        provider = _make_ollama_provider()
        cost = await provider.estimate_cost({"model": "qwen3.6", "prompt": "hello"})
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_float_type(self):
        provider = _make_ollama_provider()
        cost = await provider.estimate_cost({})
        assert isinstance(cost, float)


# ======================================================================
# 4. Image / video operations raise NotImplementedError
# ======================================================================


class TestOllamaProviderRaisesOnMediaOps:

    @pytest.mark.asyncio
    async def test_queue_prompt_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.queue_prompt({"prompt": "test"})

    @pytest.mark.asyncio
    async def test_wait_for_completion_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.wait_for_completion("job-1")

    @pytest.mark.asyncio
    async def test_get_output_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.get_output({})

    @pytest.mark.asyncio
    async def test_cancel_job_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.cancel_job("job-1")


# ======================================================================
# 5. Lifecycle no-ops (initialize, shutdown, estimate_duration)
# ======================================================================


class TestOllamaProviderLifecycle:

    @pytest.mark.asyncio
    async def test_initialize_does_not_raise(self):
        provider = _make_ollama_provider()
        await provider.initialize({})

    @pytest.mark.asyncio
    async def test_shutdown_does_not_raise(self):
        provider = _make_ollama_provider()
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_estimate_duration_returns_one(self):
        provider = _make_ollama_provider()
        duration = await provider.estimate_duration({})
        assert duration == 1.0


# ======================================================================
# 6. sync_models (OllamaProvider.sync_models)
# ======================================================================


class TestSyncOllamaModels:

    @pytest.mark.asyncio
    async def test_sync_models_returns_model_configs(self):
        """OllamaProvider.sync_models fetches /api/tags and returns ModelConfig dicts."""
        provider = _make_ollama_provider()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen3.6:latest", "size": 12345},
                {"name": "llama3.3", "size": 67890},
            ]
        }

        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=mock_resp)):
            result = await provider.sync_models()

        assert len(result) == 2
        assert result[0]["model_id"] == "qwen3.6:latest"
        assert result[0]["provider_model_id"] == "qwen3.6:latest"
        assert result[0]["display_name"] == "qwen3.6"
        assert result[0]["modality"] == "text"
        assert result[0]["endpoint_type"] == "chat_completions"
        assert result[0]["capabilities"]["supports_chat"] is True
        assert result[0]["capabilities"]["supports_tools"] is True
        assert result[0]["cost_config"]["cost"] == 0
        assert result[0]["cost_config"]["currency"] == "USD"
        assert result[0]["is_deprecated"] is False
        assert result[0]["is_active"] is True

        assert result[1]["model_id"] == "llama3.3"
        assert result[1]["display_name"] == "llama3.3"

    @pytest.mark.asyncio
    async def test_sync_models_raises_on_http_error(self):
        """sync_models wraps httpx errors in ProviderError."""
        provider = _make_ollama_provider()

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=MagicMock()
        )

        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=mock_resp)):
            with pytest.raises(ProviderError):
                await provider.sync_models()

    @pytest.mark.asyncio
    async def test_sync_models_returns_empty_list(self):
        """Returns an empty list when no models are installed."""
        provider = _make_ollama_provider()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": []}

        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=mock_resp)):
            result = await provider.sync_models()

        assert result == []


# ======================================================================
# 8. Migration: 178bb857d97b_add_ollama_provider
# ======================================================================


# Columns required by the providers table that lack DB-level defaults on SQLite.
_PROVIDER_SQL_COLS = (
    "id, name, provider_type, config, is_active, "
    "current_daily_spend, spend_reset_at, priority, created_at, updated_at"
)
_PROVIDER_SQL_VALS = (
    ":id, :name, :type, :config, :active, "
    ":spend, datetime('now'), 0, datetime('now'), datetime('now')"
)

# Columns required by model_configs table on SQLite.
_MODEL_CONFIG_SQL_COLS = (
    "id, provider_id, model_id, provider_model_id, display_name, "
    "modality, prompt_format, endpoint_type, is_active, is_deprecated, "
    "created_at, updated_at"
)
_MODEL_CONFIG_SQL_VALS = (
    ":id, :pid, :mid, :mid, :mid, "
    ":modality, 'string', :endpoint, true, false, "
    "datetime('now'), datetime('now')"
)


class TestOllamaProviderMigration:

    @pytest.mark.asyncio
    async def test_upgrade_creates_ollama_provider_row(self, db_session):
        """After migration INSERT, exactly one ollama provider exists."""
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM providers WHERE provider_type = 'ollama'")
        )
        assert result.scalar() == 0

        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {
                "id": str(uuid4()),
                "name": "Ollama (Local)",
                "type": "ollama",
                "config": '{"base_url": "http://ollama:11434"}',
                "active": True,
                "spend": 0,
            },
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT COUNT(*) FROM providers WHERE provider_type = 'ollama'")
        )
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_upgrade_idempotent_does_not_duplicate(self, db_session):
        """If an ollama provider already exists, INSERT is skipped."""
        pid = str(uuid4())
        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {
                "id": pid,
                "name": "Ollama (Local)",
                "type": "ollama",
                "config": "{}",
                "active": True,
                "spend": 0,
            },
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT 1 FROM providers WHERE provider_type = 'ollama'")
        )
        exists = result.fetchone()

        # Idempotent guard: only INSERT when no existing row
        if not exists:
            await db_session.execute(
                text(
                    f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                    f"VALUES ({_PROVIDER_SQL_VALS})"
                ),
                {
                    "id": str(uuid4()),
                    "name": "Ollama (Local)",
                    "type": "ollama",
                    "config": '{"base_url": "http://ollama:11434"}',
                    "active": True,
                    "spend": 0,
                },
            )
            await db_session.flush()

        result = await db_session.execute(
            text("SELECT COUNT(*) FROM providers WHERE provider_type = 'ollama'")
        )
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_upgrade_removes_ollama_comfyui_model_configs(self, db_session):
        """Only model_configs for ollama models with endpoint_type='comfyui' are cleaned."""
        provider_id = str(uuid4())
        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {
                "id": provider_id,
                "name": "Test ComfyUI",
                "type": "comfyui_direct",
                "config": "{}",
                "active": True,
                "spend": 0,
            },
        )

        def _insert_model_config(model_id: str, endpoint: str = "comfyui", modality: str = "text"):
            return db_session.execute(
                text(
                    f"INSERT INTO model_configs ({_MODEL_CONFIG_SQL_COLS}) "
                    f"VALUES ({_MODEL_CONFIG_SQL_VALS})"
                ),
                {
                    "id": str(uuid4()),
                    "pid": provider_id,
                    "mid": model_id,
                    "modality": modality,
                    "endpoint": endpoint,
                },
            )

        await _insert_model_config("qwen3.6:35b")
        await _insert_model_config("llama3.3")
        await _insert_model_config("flux.1-schnell", modality="image")
        await db_session.flush()

        count_before = await db_session.execute(
            text("SELECT COUNT(*) FROM model_configs")
        )
        assert count_before.scalar() == 3

        await db_session.execute(
            text(
                "DELETE FROM model_configs WHERE model_id IN ('qwen3.6:35b', 'llama3.3') "
                "AND endpoint_type = 'comfyui'"
            ),
        )
        await db_session.flush()

        count_after = await db_session.execute(
            text("SELECT COUNT(*) FROM model_configs")
        )
        assert count_after.scalar() == 1

        remaining = await db_session.execute(
            text("SELECT model_id FROM model_configs")
        )
        remaining_ids = [row[0] for row in remaining.fetchall()]
        assert "flux.1-schnell" in remaining_ids
        assert "qwen3.6:35b" not in remaining_ids
        assert "llama3.3" not in remaining_ids

    @pytest.mark.asyncio
    async def test_downgrade_removes_ollama_provider(self, db_session):
        """Downgrade DELETE removes only the ollama provider."""
        params = {
            "active": True,
            "spend": 0,
            "config": "{}",
        }

        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {**params, "id": str(uuid4()), "name": "Ollama (Local)", "type": "ollama"},
        )
        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {**params, "id": str(uuid4()), "name": "Other", "type": "comfyui_direct"},
        )
        await db_session.flush()

        count_before = await db_session.execute(
            text("SELECT COUNT(*) FROM providers")
        )
        assert count_before.scalar() == 2

        await db_session.execute(
            text("DELETE FROM providers WHERE provider_type = 'ollama'")
        )
        await db_session.flush()

        count_after = await db_session.execute(
            text("SELECT COUNT(*) FROM providers")
        )
        assert count_after.scalar() == 1

        remaining = await db_session.execute(
            text("SELECT provider_type FROM providers")
        )
        assert remaining.scalar() == "comfyui_direct"


# ======================================================================
# 9. LLMProvider interface — Wave 2 migration
# ======================================================================


def _make_ollama_provider_for_llm(
    config: dict | None = None,
) -> OllamaProvider:
    """Bare constructor for LLMProvider tests (no fixture coupling)."""
    return OllamaProvider(provider_id=uuid4(), config=config or {})


def _aiter(items: list):
    """Materialise a list as an async iterator for mocking httpx streams."""

    async def _gen():
        for it in items:
            yield it

    return _gen()


@asynccontextmanager
async def _mock_stream_response(lines: list[str], *, raise_on_status: bool = False):
    """Yield a fake httpx streaming response context manager."""

    class _FakeLineStream:
        def __init__(self, payloads: list[str]):
            self._payloads = payloads

        async def aiter_lines(self):
            for line in self._payloads:
                yield line

    class _FakeResponse:
        def __init__(self, payloads: list[str]):
            self._stream = _FakeLineStream(payloads)

        def raise_for_status(self) -> None:
            if raise_on_status:
                raise httpx.HTTPStatusError(
                    "500 Server Error",
                    request=httpx.Request("POST", "http://test/api/chat"),
                    response=httpx.Response(500),
                )

        async def aiter_lines(self):
            async for line in self._stream.aiter_lines():
                yield line

    yield _FakeResponse(lines)


class TestOllamaProviderLLMInterface:
    """Verify OllamaProvider implements the LLMProvider contract."""

    def test_inherits_from_llm_provider(self):
        provider = _make_ollama_provider_for_llm()
        assert isinstance(provider, LLMProvider)

    def test_does_not_inherit_from_image_or_video_provider(self):
        provider = _make_ollama_provider_for_llm()
        assert not isinstance(provider, ImageProvider)
        assert not isinstance(provider, VideoProvider)

    def test_capabilities_are_llm_only(self):
        provider = _make_ollama_provider_for_llm()
        caps = provider.get_capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.supports_image is False
        assert caps.supports_video is False
        assert caps.supports_llm is True
        assert caps.supports_model_sync is True

    def test_capabilities_are_frozen(self):
        caps = ProviderCapabilities(
            supports_image=False,
            supports_video=False,
            supports_llm=True,
            supports_model_sync=True,
        )
        with pytest.raises(FrozenInstanceError):
            caps.supports_llm = False  # type: ignore[misc]


class TestOllamaProviderSupportsTools:

    @pytest.mark.parametrize(
        "model,expected",
        [
            ("qwen3.6:35b", True),
            ("qwen3:32b", True),
            ("qwen2.5:7b", True),
            ("llama3.1:8b", True),
            ("llama3.2:3b", True),
            ("llama3.3:70b", True),
            ("mistral:7b", True),
            ("mixtral:8x7b", True),
            ("phi3:mini", False),
            ("gemma:7b", False),
            ("codellama:13b", False),
            ("llama2:7b", False),
            ("unknown-model:1b", False),
        ],
    )
    def test_tool_capable_families(self, model: str, expected: bool):
        provider = _make_ollama_provider_for_llm()
        assert provider.supports_tools(model) is expected


class TestOllamaProviderClassifyError:

    @pytest.mark.parametrize(
        "message,expected_cls",
        [
            ("Engine is overloaded", ProviderOverloadedError),
            ("queue is full", ProviderOverloadedError),
            ("out of memory — kill the request", ProviderOverloadedError),
            ("CUDA OOM", ProviderOverloadedError),
            ("HIP OOM detected", ProviderOverloadedError),
            ("rate limit exceeded", ProviderRateLimitError),
            ("HTTP 429 Too Many Requests", ProviderRateLimitError),
            ("connection refused", ProviderConnectionError),
            ("ConnectionError: failed", ProviderConnectionError),
            ("Read timed out", ProviderTimeoutError),
            ("model 'foo' not found", ProviderError),
            ("Invalid API key", ProviderError),
            ("Something weird happened", ProviderError),
        ],
    )
    def test_classifies_known_patterns(
        self,
        message: str,
        expected_cls: type[ProviderError],
    ):
        provider = _make_ollama_provider_for_llm()
        result = provider.classify_error(Exception(message))
        assert isinstance(result, expected_cls)
        assert str(result) == message

    def test_inherits_provider_base_default(self):
        provider = _make_ollama_provider_for_llm()
        result = provider.classify_error(Exception("boom"))
        assert isinstance(result, ProviderError)


class TestOllamaProviderChatStream:

    @pytest.mark.asyncio
    async def test_yields_text_and_done_chunks(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        lines = [
            json.dumps({"message": {"content": "Hello "}, "done": False}),
            json.dumps({"message": {"content": "world"}, "done": False}),
            json.dumps(
                {
                    "message": {},
                    "done": True,
                    "prompt_eval_count": 12,
                    "eval_count": 7,
                }
            ),
        ]

        from contextlib import asynccontextmanager as _acm

        @_acm
        async def _stream_ctx():
            class _Resp:
                def raise_for_status(self):
                    pass

                async def aiter_lines(self):
                    for line in lines:
                        yield line

            yield _Resp()

        with patch.object(
            provider._client,
            "stream",
            return_value=_stream_ctx(),
        ):
            chunks: list[LLMChunk] = []
            async for c in provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3.6:35b",
            ):
                chunks.append(c)

        assert [c.type for c in chunks] == ["text", "text", "usage", "done"]
        assert chunks[0].content == "Hello "
        assert chunks[1].content == "world"
        assert chunks[2].tokens_in == 12
        assert chunks[2].tokens_out == 7
        assert chunks[3].content is None

        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_stream_propagates_ollama_error_chunk(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        lines = [json.dumps({"error": "model 'broken' not found"})]

        from contextlib import asynccontextmanager as _acm

        @_acm
        async def _stream_ctx():
            class _Resp:
                def raise_for_status(self):
                    pass

                async def aiter_lines(self):
                    for line in lines:
                        yield line

            yield _Resp()

        with patch.object(
            provider._client,  # type: ignore[attr-defined]
            "stream",
            return_value=_stream_ctx(),
        ):
            with pytest.raises(LLMError, match="model 'broken' not found"):
                async for _ in provider.chat_stream(
                    messages=[{"role": "user", "content": "hi"}],
                    model="broken",
                ):
                    pass

        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_stream_raises_without_done_chunk(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        lines = [json.dumps({"message": {"content": "partial"}, "done": False})]

        from contextlib import asynccontextmanager as _acm

        @_acm
        async def _stream_ctx():
            class _Resp:
                def raise_for_status(self):
                    pass

                async def aiter_lines(self):
                    for line in lines:
                        yield line

            yield _Resp()

        with patch.object(
            provider._client,  # type: ignore[attr-defined]
            "stream",
            return_value=_stream_ctx(),
        ):
            with pytest.raises(LLMError, match="ended without a done chunk"):
                async for _ in provider.chat_stream(
                    messages=[{"role": "user", "content": "hi"}],
                    model="qwen3.6:35b",
                ):
                    pass

        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_forwards_tools_in_payload(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        captured: dict = {}

        @asynccontextmanager
        async def _stream_ctx():
            class _Resp:
                def raise_for_status(self):
                    pass

                async def aiter_lines(self):
                    yield json.dumps(
                        {"message": {"content": "ok"}, "done": True}
                    )

            yield _Resp()

        def _capture_stream(method, url, json=None, **_):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            return _stream_ctx()

        with patch.object(
            provider._client,
            "stream",
            side_effect=_capture_stream,
        ):
            tools = [{"type": "function", "function": {"name": "lookup"}}]
            chunks = []
            async for c in provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3.6:35b",
                tools=tools,
            ):
                chunks.append(c)

        assert captured["json"]["tools"] == tools
        assert captured["json"]["stream"] is True
        assert captured["json"]["model"] == "qwen3.6:35b"

        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_uses_default_model_when_none_passed(self):
        provider = _make_ollama_provider_for_llm(
            config={
                "base_url": "http://test-ollama:11434",
                "default_model": "llama3.3:70b",
            }
        )
        await provider.initialize({})

        captured: dict = {}

        @asynccontextmanager
        async def _stream_ctx():
            class _Resp:
                def raise_for_status(self):
                    pass

                async def aiter_lines(self):
                    yield json.dumps({"message": {"content": "ok"}, "done": True})

            yield _Resp()

        def _capture_stream(method, url, json=None, **_):
            captured["json"] = json
            return _stream_ctx()

        with patch.object(
            provider._client,
            "stream",
            side_effect=_capture_stream,
        ):
            chunks = []
            async for c in provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                model="",
            ):
                chunks.append(c)

        assert captured["json"]["model"] == "llama3.3:70b"
        await provider.shutdown()


class TestOllamaProviderChat:

    @pytest.mark.asyncio
    async def test_returns_complete_response_in_single_text_chunk(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        response_payload = {
            "message": {"role": "assistant", "content": "full answer"},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 4,
        }
        mock_post = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: response_payload,
            )
        )
        with patch.object(provider._client, "post", mock_post):  # type: ignore[attr-defined]
            chunks = []
            async for c in provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3.6:35b",
            ):
                chunks.append(c)

        types = [c.type for c in chunks]
        assert types[-1] == "done"
        text_chunks = [c for c in chunks if c.type == "text"]
        assert len(text_chunks) == 1
        assert text_chunks[0].content == "full answer"
        assert chunks[-2].type == "usage"
        assert chunks[-2].tokens_in == 5
        assert chunks[-2].tokens_out == 4

        sent = mock_post.call_args.kwargs["json"]
        assert sent["stream"] is False
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_surfaces_ollama_error(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        mock_post = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: {"error": "model not found"},
            )
        )
        with patch.object(provider._client, "post", mock_post):  # type: ignore[attr-defined]
            with pytest.raises(LLMError, match="model not found"):
                async for _ in provider.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    model="missing",
                ):
                    pass

        await provider.shutdown()


class TestOllamaProviderSyncModels:

    @pytest.mark.asyncio
    async def test_calls_api_tags_endpoint(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        api_tags_payload = {
            "models": [
                {"name": "qwen3.6:35b", "size": 20_000_000_000},
                {"name": "llama3.3:70b", "size": 40_000_000_000},
            ]
        }
        mock_get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: api_tags_payload,
            )
        )
        with patch.object(provider._client, "get", mock_get):  # type: ignore[attr-defined]
            result = await provider.sync_models()

        mock_get.assert_awaited_once_with("http://test-ollama:11434/api/tags")
        assert len(result) == 2
        first = result[0]
        assert first["model_id"] == "qwen3.6:35b"
        assert first["display_name"] == "qwen3.6"
        assert first["modality"] == "text"
        assert first["endpoint_type"] == "chat_completions"
        assert first["capabilities"]["supports_chat"] is True
        assert first["capabilities"]["supports_tools"] is True
        assert first["cost_config"] == {"cost": 0, "currency": "USD"}
        assert first["is_deprecated"] is False
        assert first["is_active"] is True

        second = result[1]
        assert second["model_id"] == "llama3.3:70b"
        assert second["display_name"] == "llama3.3"
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_sync_models_always_refreshes(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        mock_get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: {"models": [{"name": "phi3:mini"}]},
            )
        )
        with patch.object(provider._client, "get", mock_get):
            first = await provider.sync_models()
            second = await provider.sync_models()

        assert first == second
        assert mock_get.await_count == 2
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_sync_models_maps_non_tool_capable_family(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        mock_get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: {"models": [{"name": "phi3:mini"}]},
            )
        )
        with patch.object(provider._client, "get", mock_get):  # type: ignore[attr-defined]
            result = await provider.sync_models()

        assert result[0]["capabilities"]["supports_tools"] is False
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_sync_models_classifies_http_error(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        mock_get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        with patch.object(provider._client, "get", mock_get):  # type: ignore[attr-defined]
            with pytest.raises(ProviderConnectionError):
                await provider.sync_models()

        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_empty_model_list_returns_empty(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        mock_get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: {"models": []},
            )
        )
        with patch.object(provider._client, "get", mock_get):  # type: ignore[attr-defined]
            result = await provider.sync_models()

        assert result == []
        await provider.shutdown()


class TestOllamaProviderListModels:

    @pytest.mark.asyncio
    async def test_returns_raw_ollama_payload(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        raw = {
            "models": [
                {
                    "name": "qwen3.6:35b",
                    "size": 20_000_000_000,
                    "modified_at": "2025-01-01T00:00:00Z",
                    "details": {"family": "qwen3"},
                }
            ]
        }
        mock_get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: raw,
            )
        )
        with patch.object(provider._client, "get", mock_get):  # type: ignore[attr-defined]
            models = await provider.list_models()

        assert models == raw["models"]
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_uses_cache_on_subsequent_calls(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        mock_get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: {"models": [{"name": "phi3:mini", "size": 1}]},
            )
        )
        with patch.object(provider._client, "get", mock_get):  # type: ignore[attr-defined]
            first = await provider.list_models()
            second = await provider.list_models()

        assert first == second
        assert mock_get.await_count == 1
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_cache_clears_on_shutdown(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        mock_get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=lambda: None,
                json=lambda: {"models": [{"name": "phi3:mini"}]},
            )
        )
        with patch.object(provider._client, "get", mock_get):
            first = await provider.list_models()
            assert first == [{"name": "phi3:mini"}]

            await provider.shutdown()
            await provider.initialize({})
            mock_get2 = AsyncMock(
                return_value=MagicMock(
                    raise_for_status=lambda: None,
                    json=lambda: {"models": [{"name": "qwen3.6:35b"}]},
                )
            )
            with patch.object(provider._client, "get", mock_get2):
                second = await provider.list_models()
            assert second == [{"name": "qwen3.6:35b"}]

        await provider.shutdown()


class TestOllamaProviderVisionMessages:
    """OllamaProvider can carry image payloads through the same chat() entry point."""

    @pytest.mark.asyncio
    async def test_converts_data_url_image_to_ollama_format(self):
        provider = _make_ollama_provider_for_llm(
            config={"base_url": "http://test-ollama:11434"}
        )
        await provider.initialize({})

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AAAA"},
                    },
                ],
            }
        ]
        converted = OllamaProvider._convert_messages_for_ollama(messages)
        assert converted[0]["content"] == "what is in this image?"
        assert converted[0]["images"] == ["AAAA"]

    def test_passes_through_string_content(self):
        out = OllamaProvider._convert_messages_for_ollama(
            [{"role": "user", "content": "hi"}]
        )
        assert out == [{"role": "user", "content": "hi"}]

    def test_image_url_without_data_prefix_kept_as_text_marker(self):
        out = OllamaProvider._convert_messages_for_ollama(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "http://x/y.png"}}
                    ],
                }
            ]
        )
        assert out[0]["content"] == "[Image: http://x/y.png]"
        assert "images" not in out[0]
