"""LLM-only provider for local Ollama models (Qwen, Llama, etc).

Implements the ``LLMProvider`` interface — text/chat completions and model
sync only. Does NOT support image or video generation. Legacy
``ComfyUIProvider``-style methods (``queue_prompt``, ``wait_for_completion``,
``get_output``, ``cancel_job``, ``estimate_cost``, ``estimate_duration``) are
preserved as no-op or ``NotImplementedError`` shims for backward compatibility
with existing call sites.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID

import httpx

from app.config import get_settings
from app.services.llm_service import LLMChunk, LLMError
from app.services.providers.base import (
    LLMProvider,
    ProviderCapabilities,
    ProviderError,
    ProviderInfo,
    ProviderOverloadedError,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Text/chat LLM provider for local Ollama runtime.

    Talks to Ollama's native HTTP API at ``{base_url}/api/chat`` and
    ``/api/tags``. Supports streaming chat, model listing/sync, and tool
    calling for capable model families (Qwen2/3, Llama3.1+).
    """

    _TOOL_CAPABLE_FAMILIES: tuple[str, ...] = (
        "qwen2",
        "qwen3",
        "llama3.1",
        "llama3.2",
        "llama3.3",
        "mistral",
        "mixtral",
        "command-r",
        "firefunction",
        "nemotron",
    )

    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.base_url = (
            config.get("base_url")
            or get_settings().ollama_url
            or "http://ollama:11434"
        ).rstrip("/")
        self._default_model: str = (
            config.get("default_model") or get_settings().llm_model
        )
        self._client: httpx.AsyncClient | None = None
        self._cached_models: list[dict[str, Any]] | None = None

    async def initialize(self, config: dict) -> None:
        """Apply config overrides and lazily build the HTTP client."""
        if "base_url" in config and config["base_url"]:
            self.base_url = config["base_url"].rstrip("/")
        if "default_model" in config and config["default_model"]:
            self._default_model = config["default_model"]
        if self._client is None:
            timeout = get_settings().llm_timeout_seconds
            self._client = httpx.AsyncClient(timeout=timeout)

    async def shutdown(self) -> None:
        """Close the HTTP client if it was created."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._cached_models = None

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(
            name="Ollama",
            provider_type="ollama",
            is_available=True,
            cost_per_job=0.0,
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_image=False,
            supports_video=False,
            supports_llm=True,
            supports_model_sync=True,
        )

    def classify_error(self, exc: Exception) -> ProviderError:
        """Map arbitrary exceptions to provider-specific error types.

        Ollama surfaces a small set of distinctive strings we recognise
        before falling back to the base ``ProviderBase.classify_error``
        pattern matcher (overloaded / 429 / connection / timeout).
        """
        msg = str(exc).lower()

        # Ollama-specific: out-of-memory and process crashes are capacity issues
        if "out of memory" in msg or "cuda oom" in msg or "hip oom" in msg:
            return ProviderOverloadedError(str(exc))

        # Generic "model not found" — keep as a plain ProviderError so callers
        # can decide whether to surface a validation error.
        if "model" in msg and "not found" in msg:
            return ProviderError(str(exc))

        # Default base-class matcher handles overloaded/429/connection/timeout
        return super().classify_error(exc)

    def supports_tools(self, model: str) -> bool:
        """Return True if the named Ollama model supports tool calling."""
        base = model.lower().split(":", 1)[0]
        for family in self._TOOL_CAPABLE_FAMILIES:
            if base == family or base.startswith(family + ".") or base.startswith(family + "-"):
                return True
        return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        """Non-streaming chat — collects a single complete response.

        Internally calls ``/api/chat`` with ``stream=false`` and yields one
        ``text`` chunk plus a final ``usage`` and ``done`` chunk.
        """
        async for chunk in self._run_chat(messages, model, stream=False, **kwargs):
            yield chunk

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        """Streaming chat — yields ``text`` chunks as they arrive from Ollama.

        Forwards the same wire format as ``chat()``; callers that do not
        care about streaming granularity can ignore everything except the
        final ``done`` chunk.
        """
        async for chunk in self._run_chat(messages, model, stream=True, **kwargs):
            yield chunk

    async def sync_models(self) -> list[dict[str, Any]]:
        """Fetch the locally-available model list from ``/api/tags``.

        Returns a list of dicts shaped to match the ``ModelConfig`` table —
        one entry per installed model. The list is also cached for the
        lifetime of this provider instance so subsequent ``list_models()``
        calls don't re-hit the network.
        """
        client = await self._ensure_client()
        try:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise self.classify_error(exc) from exc

        raw_models = data.get("models", [])
        self._cached_models = list(raw_models)
        return [self._model_to_config(m) for m in raw_models]

    async def list_models(self) -> list[dict[str, Any]]:
        """Return the cached model list, syncing from Ollama if necessary.

        The returned dicts mirror Ollama's raw ``/api/tags`` payload
        (``name``, ``size``, ``modified_at``, ``details``, …) — useful for
        admin UIs that need full metadata.
        """
        if self._cached_models is not None:
            return list(self._cached_models)
        await self.sync_models()
        return list(self._cached_models or [])

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            await self.initialize({})
        assert self._client is not None, "client must be initialised"
        return self._client

    async def _run_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        stream: bool,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        """Shared chat implementation for both ``chat`` and ``chat_stream``."""
        client = await self._ensure_client()
        ollama_messages = self._convert_messages_for_ollama(messages)

        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": ollama_messages,
            "stream": stream,
        }
        tools = kwargs.get("tools")
        if tools is not None:
            payload["tools"] = tools

        target_model = payload["model"]

        try:
            if stream:
                async for chunk in self._stream_chat(client, payload, target_model):
                    yield chunk
            else:
                async for chunk in self._blocking_chat(client, payload, target_model):
                    yield chunk
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(
                f"LLM request failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        target_model: str,
    ) -> AsyncIterator[LLMChunk]:
        async with client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LLMError(f"Invalid streamed LLM response: {line}") from exc

                if data.get("error"):
                    raise LLMError(str(data["error"]))

                message = data.get("message") or {}
                content = message.get("content")
                if content:
                    yield LLMChunk(type="text", content=content)

                if data.get("done"):
                    tokens_in = data.get("prompt_eval_count")
                    tokens_out = data.get("eval_count")
                    if tokens_in is not None or tokens_out is not None:
                        yield LLMChunk(
                            type="usage",
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                        )
                    yield LLMChunk(type="done")
                    return

        # Stream ended without a done chunk
        raise LLMError("LLM stream ended without a done chunk")

    async def _blocking_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        target_model: str,
    ) -> AsyncIterator[LLMChunk]:
        response = await client.post(
            f"{self.base_url}/api/chat", json=payload
        )
        response.raise_for_status()
        data = response.json()

        if data.get("error"):
            raise LLMError(str(data["error"]))

        message = data.get("message") or {}
        content = message.get("content") or ""
        yield LLMChunk(type="text", content=content)

        tokens_in = data.get("prompt_eval_count")
        tokens_out = data.get("eval_count")
        if tokens_in is not None or tokens_out is not None:
            yield LLMChunk(
                type="usage",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        yield LLMChunk(type="done")

    @staticmethod
    def _model_to_config(raw: dict[str, Any]) -> dict[str, Any]:
        """Translate an Ollama ``/api/tags`` entry to a ModelConfig-shaped dict."""
        name = raw.get("name", "")
        display = name.split(":", 1)[0] if ":" in name else name
        return {
            "model_id": name,
            "provider_model_id": name,
            "display_name": display,
            "modality": "text",
            "endpoint_type": "chat_completions",
            "capabilities": {
                "supports_chat": True,
                "supports_tools": OllamaProvider._supports_model_name(name),
            },
            "cost_config": {"cost": 0, "currency": "USD"},
            "is_deprecated": False,
            "is_active": True,
        }

    @classmethod
    def _supports_model_name(cls, model_name: str) -> bool:
        base = model_name.lower().split(":", 1)[0]
        for family in cls._TOOL_CAPABLE_FAMILIES:
            if base == family or base.startswith(family + ".") or base.startswith(family + "-"):
                return True
        return False

    @staticmethod
    def _convert_messages_for_ollama(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-style vision messages to Ollama's native format.

        OpenAI: ``content=[{"type":"text",...}, {"type":"image_url",...}]``
        Ollama: ``content="text"`` plus ``images=["base64string"]``
        """
        converted: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                text_parts: list[str] = []
                images: list[str] = []
                for part in content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            b64 = url.split(",", 1)[-1] if "," in url else url
                            images.append(b64)
                        else:
                            text_parts.append(f"[Image: {url}]")
                new_msg = dict(msg)
                new_msg["content"] = "\n".join(text_parts)
                if images:
                    new_msg["images"] = images
                converted.append(new_msg)
            else:
                converted.append(msg)
        return converted

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 1.0

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        raise NotImplementedError("Ollama is text-only")

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 172800.0,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict:
        raise NotImplementedError("Ollama is text-only")

    async def get_output(self, result: dict) -> bytes | None:
        raise NotImplementedError("Ollama is text-only")

    async def cancel_job(self, job_id: str) -> bool:
        raise NotImplementedError("Ollama is text-only")
