from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from app.services.llm_service import LLMChunk
from app.services.providers.base import (
    ImageProvider,
    LLMProvider,
    ProviderBase,
    ProviderCapabilities,
    ProviderConnectionError,
    ProviderError,
    ProviderInfo,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    VideoProvider,
)


def test_provider_base_has_expected_abstract_methods() -> None:
    abstract_methods = ProviderBase.__abstractmethods__
    assert "initialize" in abstract_methods
    assert "shutdown" in abstract_methods
    assert "get_status" in abstract_methods
    assert "get_capabilities" in abstract_methods
    assert "classify_error" not in abstract_methods


def test_provider_base_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        ProviderBase()  # type: ignore[abstract]


def test_image_video_llm_abc_expected_methods() -> None:
    assert "generate_image" in ImageProvider.__abstractmethods__
    assert "generate_video" in VideoProvider.__abstractmethods__

    llm_abstracts = LLMProvider.__abstractmethods__
    assert "chat" in llm_abstracts
    assert "chat_stream" in llm_abstracts
    assert "supports_tools" in llm_abstracts


def test_provider_capabilities_defaults_and_frozen_behavior() -> None:
    caps = ProviderCapabilities()
    assert caps.supports_image is False
    assert caps.supports_video is False
    assert caps.supports_llm is False
    assert caps.supports_model_sync is False

    with pytest.raises(FrozenInstanceError):
        caps.supports_image = True  # type: ignore[misc]


def test_provider_error_hierarchy() -> None:
    overloaded = ProviderOverloadedError("busy")
    rate_limited = ProviderRateLimitError("429")
    connection = ProviderConnectionError("down")
    timeout = ProviderTimeoutError("timeout")

    assert isinstance(overloaded, ProviderError)
    assert isinstance(rate_limited, ProviderError)
    assert isinstance(connection, ProviderError)
    assert isinstance(timeout, ProviderError)
    assert isinstance(overloaded, Exception)


class _ConcreteProviderBase(ProviderBase):
    async def initialize(self, config: dict[str, Any]) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(name="test", provider_type="test", is_available=True)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def classify_error(self, exc: Exception) -> ProviderError:
        return ProviderError(str(exc))


@pytest.mark.asyncio
async def test_provider_base_default_model_methods_raise_not_implemented() -> None:
    provider = _ConcreteProviderBase()

    with pytest.raises(NotImplementedError):
        await provider.sync_models()

    with pytest.raises(NotImplementedError):
        await provider.list_models()


class _ConcreteLLMProvider(LLMProvider):
    async def initialize(self, config: dict[str, Any]) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(name="llm", provider_type="llm", is_available=True)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_llm=True)

    def classify_error(self, exc: Exception) -> ProviderError:
        return ProviderError(str(exc))

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        async def _generator() -> AsyncIterator[LLMChunk]:
            yield LLMChunk(type="done")

        return _generator()

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        async def _generator() -> AsyncIterator[LLMChunk]:
            yield LLMChunk(type="done")

        return _generator()

    def supports_tools(self, model: str) -> bool:
        return model.startswith("tools:")


@pytest.mark.asyncio
async def test_llm_provider_chat_contract_uses_llmchunk() -> None:
    provider = _ConcreteLLMProvider()
    chunks = [chunk async for chunk in provider.chat([], "test")]
    assert len(chunks) == 1
    assert isinstance(chunks[0], LLMChunk)
    assert chunks[0].type == "done"
