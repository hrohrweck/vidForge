"""Tests for refactored resolve_llm() using provider registry.

Verifies that resolve_llm:
- Resolves model via ModelConfig → registry.create() → LLMProvider
- Falls back to LLMClient when no model_config found
- Validates returned instance implements LLMProvider
- Handles DB session management (none provided vs provided)
- Propagates errors from registry.create()
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.llm_service import LLMChunk, LLMClient, LLMError, resolve_llm
from app.services.providers.base import LLMProvider, ProviderCapabilities, ProviderInfo


class FakeLLMProvider(LLMProvider):
    """Minimal LLMProvider for testing registry.create() integration."""

    def __init__(self, provider_id: Any, config: dict[str, Any]) -> None:
        self.provider_id = provider_id
        self.config = config
        self.initialized_with: dict[str, Any] | None = None
        self.shutdown_called = False

    async def initialize(self, config: dict[str, Any]) -> None:
        self.initialized_with = config

    async def shutdown(self) -> None:
        self.shutdown_called = True

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(name="fake", provider_type="fake", is_available=True)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_llm=True)

    def chat(self, messages, model, **kwargs):
        yield LLMChunk(type="text", content="fake response")
        yield LLMChunk(type="done")

    def chat_stream(self, messages, model, **kwargs):
        yield LLMChunk(type="text", content="fake")
        yield LLMChunk(type="done")

    def supports_tools(self, model: str) -> bool:
        return False


class FakeNonLLMProvider:
    """Provider that does NOT implement LLMProvider — for negative tests."""

    def __init__(self, provider_id: Any, config: dict[str, Any]) -> None:
        self.provider_id = provider_id
        self.config = config

    async def initialize(self, config: dict[str, Any]) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(name="non-llm", provider_type="nonllm", is_available=True)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_image=True)


@pytest.fixture
def fake_provider_record() -> MagicMock:
    record = MagicMock()
    record.id = uuid4()
    record.provider_type = "fake"
    record.config = {"api_key": "test-key", "default_model": "test-model"}
    record.is_active = True
    return record


@pytest.fixture
def fake_model_config(fake_provider_record: MagicMock) -> MagicMock:
    config = MagicMock()
    config.model_id = "test-model-id"
    config.is_active = True
    config.provider = fake_provider_record
    return config


@pytest.fixture
def mock_db_session(fake_model_config: MagicMock) -> MagicMock:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_model_config
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ── resolve_llm registry integration tests ──────────────────────────────

REGISTRY_CREATE_PATH = "app.services.providers.registry.create"


@pytest.mark.asyncio
async def test_resolve_llm_uses_registry_create(
    mock_db_session: MagicMock,
    fake_model_config: MagicMock,
):
    fake_instance = FakeLLMProvider(uuid4(), {})

    with patch(REGISTRY_CREATE_PATH, new=AsyncMock(return_value=fake_instance)) as mock_create:
        result = await resolve_llm("test-model-id", db=mock_db_session)

    assert result is fake_instance
    mock_create.assert_awaited_once()
    args = mock_create.call_args[0]
    assert args[0] == "fake"  # provider_type
    assert args[1] == fake_model_config.provider.id
    assert args[2] == fake_model_config.provider.config


@pytest.mark.asyncio
async def test_resolve_llm_verifies_llm_provider(
    mock_db_session: MagicMock,
    fake_model_config: MagicMock,
):
    fake_model_config.provider.provider_type = "nonllm"
    non_llm_instance = FakeNonLLMProvider(uuid4(), {})

    with patch(REGISTRY_CREATE_PATH, new=AsyncMock(return_value=non_llm_instance)):
        with pytest.raises(LLMError, match="does not support LLM operations"):
            await resolve_llm("test-model-id", db=mock_db_session)


@pytest.mark.asyncio
async def test_resolve_llm_returns_llm_provider_instance(
    mock_db_session: MagicMock,
):
    instance = FakeLLMProvider(uuid4(), {})

    with patch(REGISTRY_CREATE_PATH, new=AsyncMock(return_value=instance)):
        result = await resolve_llm("test-model-id", db=mock_db_session)

    assert isinstance(result, LLMProvider)
    assert result is instance


@pytest.mark.asyncio
async def test_resolve_llm_fallback_when_no_model_config(
    mock_db_session: MagicMock,
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    result = await resolve_llm("nonexistent-model", db=mock_db_session)
    assert isinstance(result, LLMClient)


@pytest.mark.asyncio
async def test_resolve_llm_fallback_when_model_config_has_no_provider(
    mock_db_session: MagicMock,
    fake_model_config: MagicMock,
):
    fake_model_config.provider = None

    result = await resolve_llm("orphan-model", db=mock_db_session)
    assert isinstance(result, LLMClient)


@pytest.mark.asyncio
async def test_resolve_llm_fallback_on_db_exception(
    mock_db_session: MagicMock,
):
    mock_db_session.execute = AsyncMock(side_effect=RuntimeError("DB down"))

    result = await resolve_llm("any-model", db=mock_db_session)
    assert isinstance(result, LLMClient)


@pytest.mark.asyncio
async def test_resolve_llm_fallback_on_registry_create_failure(
    mock_db_session: MagicMock,
):
    with patch(REGISTRY_CREATE_PATH, new=AsyncMock(side_effect=ValueError("Unknown provider"))):
        result = await resolve_llm("test-model-id", db=mock_db_session)

    assert isinstance(result, LLMClient)


@pytest.mark.asyncio
async def test_resolve_llm_propagates_llm_error_from_registry(
    mock_db_session: MagicMock,
):
    with patch(
        REGISTRY_CREATE_PATH, new=AsyncMock(side_effect=LLMError("custom LLM error"))
    ):
        with pytest.raises(LLMError, match="custom LLM error"):
            await resolve_llm("test-model-id", db=mock_db_session)


@pytest.mark.asyncio
async def test_resolve_llm_creates_db_session_when_none_provided(
    fake_model_config: MagicMock,
):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_model_config
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    # Mock the entire ctx module since session_factory is a property
    mock_ctx = MagicMock()
    mock_ctx.session_factory = mock_session_factory

    fake_instance = FakeLLMProvider(uuid4(), {})

    with patch(
        "app.workers.context.ctx", new=mock_ctx
    ), patch(REGISTRY_CREATE_PATH, new=AsyncMock(return_value=fake_instance)):
        result = await resolve_llm("test-model-id")

    assert result is fake_instance


@pytest.mark.asyncio
async def test_resolve_llm_passes_provider_config_to_registry(
    mock_db_session: MagicMock,
    fake_model_config: MagicMock,
):
    fake_model_config.provider.config = {
        "api_key": "sk-abc",
        "base_url": "https://custom.example.com",
        "default_model": "gpt-4",
    }
    fake_instance = FakeLLMProvider(uuid4(), {})

    with patch(REGISTRY_CREATE_PATH, new=AsyncMock(return_value=fake_instance)) as mock_create:
        await resolve_llm("test-model-id", db=mock_db_session)

    config_arg = mock_create.call_args[0][2]
    assert config_arg["api_key"] == "sk-abc"
    assert config_arg["base_url"] == "https://custom.example.com"
    assert config_arg["default_model"] == "gpt-4"


@pytest.mark.asyncio
async def test_resolve_llm_no_prefix_fallback_logic():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    # "poe:" and "atlascloud:" prefixed model_ids now just go through
    # normal DB lookup — no special prefix handling exists anymore.
    result = await resolve_llm("poe:some-model", db=mock_session)
    assert isinstance(result, LLMClient)

    result = await resolve_llm("atlascloud:another-model", db=mock_session)
    assert isinstance(result, LLMClient)


@pytest.mark.asyncio
async def test_resolve_llm_uses_provider_type_from_db(
    mock_db_session: MagicMock,
    fake_model_config: MagicMock,
):
    fake_model_config.provider.provider_type = "ollama"
    fake_instance = FakeLLMProvider(uuid4(), {})

    with patch(REGISTRY_CREATE_PATH, new=AsyncMock(return_value=fake_instance)) as mock_create:
        await resolve_llm("test-model-id", db=mock_db_session)

    assert mock_create.call_args[0][0] == "ollama"


def test_resolve_llm_no_hardcoded_provider_branches():
    import inspect

    source = inspect.getsource(resolve_llm)
    assert '"poe"' not in source
    assert '"atlascloud"' not in source
    assert "startswith" not in source


# ── Backward compatibility tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_client_still_instantiable():
    client = LLMClient(model="test-model")
    assert client.model == "test-model"
    assert client.client is not None
    await client.close()


def test_llmchunk_dataclass_unchanged():
    chunk = LLMChunk(type="text", content="hello")
    assert chunk.type == "text"
    assert chunk.content == "hello"
    assert chunk.tool_calls is None

    tool_chunk = LLMChunk(type="tool_call", tool_calls=[{"name": "test"}])
    assert tool_chunk.type == "tool_call"
    assert tool_chunk.tool_calls == [{"name": "test"}]


def test_llmerror_exception_unchanged():
    with pytest.raises(LLMError, match="test error"):
        raise LLMError("test error")

    try:
        raise LLMError("test")
    except Exception as e:
        assert str(e) == "test"
