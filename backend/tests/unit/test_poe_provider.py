import base64
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.services.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.services.providers.poe import PoeProvider


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str = "",
        content: bytes = b"",
    ):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.content = content

    def json(self) -> dict[str, Any]:
        return self._json_data

    async def aread(self) -> bytes:
        return self.text.encode("utf-8")


class FakeStreamResponse:
    def __init__(
        self,
        lines: list[str],
        status_code: int = 200,
        error_body: str = "",
    ):
        self._lines = lines
        self.status_code = status_code
        self._error_body = error_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return self._error_body.encode("utf-8")


class FakeClient:
    def __init__(self):
        self.get_responses: dict[str, FakeResponse] = {}
        self.post_responses: dict[str, FakeResponse] = {}
        self.stream_response: FakeStreamResponse | None = None
        self.get_requests: list[dict[str, Any]] = []
        self.post_requests: list[dict[str, Any]] = []
        self.stream_requests: list[dict[str, Any]] = []

    async def get(self, url: str, headers: dict[str, str]) -> FakeResponse:
        self.get_requests.append({"url": url, "headers": headers})
        return self.get_responses[url]

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
        self.post_requests.append({"url": url, "json": json, "headers": headers})
        return self.post_responses[url]

    def stream(
        self,
        method: str,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> FakeStreamResponse:
        self.stream_requests.append(
            {"method": method, "url": url, "json": json, "headers": headers}
        )
        if self.stream_response is None:
            raise RuntimeError("stream_response not configured")
        return self.stream_response


def _provider_with_client(client: FakeClient) -> PoeProvider:
    provider = PoeProvider(uuid4(), {"api_key": "test-key"})
    provider.client = client  # type: ignore[assignment]
    return provider


@pytest.mark.asyncio
async def test_capabilities_and_supports_tools_cache() -> None:
    provider = PoeProvider(uuid4(), {"api_key": "test-key"})

    caps = provider.get_capabilities()
    assert caps.supports_image is True
    assert caps.supports_video is True
    assert caps.supports_llm is True
    assert caps.supports_model_sync is True

    provider._models_without_tools = {"no-tools-model"}
    assert provider.supports_tools("no-tools-model") is False
    assert provider.supports_tools("tools-model") is True


@pytest.mark.asyncio
async def test_chat_streaming_and_chat_wrapper() -> None:
    client = FakeClient()
    client.stream_response = FakeStreamResponse(
        lines=[
            'data: {"choices":[{"delta":{"content":"Hi"}}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}',
            "data: [DONE]",
        ]
    )
    provider = _provider_with_client(client)

    chunks = [
        chunk
        async for chunk in provider.chat(
            [{"role": "user", "content": "hello"}],
            model="GPT-5",
        )
    ]

    assert [chunk.type for chunk in chunks] == ["text", "usage", "done", "done"]
    assert chunks[0].content == "Hi"
    assert chunks[1].tokens_in == 3
    assert chunks[1].tokens_out == 2

    assert len(client.stream_requests) == 1
    assert client.stream_requests[0]["url"] == "https://api.poe.com/v1/chat/completions"
    assert client.stream_requests[0]["json"]["stream"] is True


@pytest.mark.asyncio
async def test_generate_image_returns_asset_id_and_bytes() -> None:
    image_payload = json.dumps(
        {"image_base64": base64.b64encode(b"image-bytes").decode("ascii")}
    )

    client = FakeClient()
    client.post_responses["https://api.poe.com/v1/chat/completions"] = FakeResponse(
        status_code=200,
        json_data={
            "id": "img-123",
            "choices": [{"message": {"content": image_payload}}],
        },
    )
    provider = _provider_with_client(client)

    asset_id, image_bytes = await provider.generate_image(
        prompt="a landscape",
        model="GPT-Image-1",
        aspect_ratio="1:1",
    )

    assert asset_id == "img-123"
    assert image_bytes == b"image-bytes"
    assert client.post_requests[0]["json"]["model"] == "GPT-Image-1"


@pytest.mark.asyncio
async def test_generate_video_returns_asset_id_and_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    video_payload = json.dumps(
        {"video_base64": base64.b64encode(b"video-bytes").decode("ascii")}
    )

    async def _no_config(*_args: Any, **_kwargs: Any) -> None:
        return None

    client = FakeClient()
    client.post_responses["https://api.poe.com/v1/chat/completions"] = FakeResponse(
        status_code=200,
        json_data={
            "id": "vid-123",
            "choices": [{"message": {"content": video_payload}}],
        },
    )
    provider = _provider_with_client(client)
    monkeypatch.setattr(provider, "_get_model_config", _no_config)

    asset_id, video_bytes = await provider.generate_video(
        prompt="a flying drone shot",
        model="Veo-3",
        duration=6,
        aspect_ratio="16:9",
    )

    assert asset_id == "vid-123"
    assert video_bytes == b"video-bytes"
    assert client.post_requests[0]["json"]["model"] == "Veo-3"


@pytest.mark.asyncio
async def test_sync_models_normalizes_poe_models_and_updates_cache() -> None:
    raw_models = [
        {
            "id": "Poe-Text-Tools",
            "root": "poe-text-tools",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "supported_features": ["tools", "web_search"],
            "supported_endpoints": ["/v1/chat/completions"],
            "context_window": {"context_length": 200000, "max_output_tokens": 8000},
            "pricing": {"currency": "compute_points", "compute_points": 15},
            "metadata": {"display_name": "Poe Text Tools"},
        },
        {
            "id": "Poe-Video-NoTools",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["video"],
            },
            "supported_features": [],
            "supported_endpoints": ["/v1/videos"],
            "metadata": {"display_name": "Poe Video"},
        },
    ]

    client = FakeClient()
    client.get_responses["https://api.poe.com/v1/models"] = FakeResponse(
        status_code=200,
        json_data={"data": raw_models},
    )
    provider = _provider_with_client(client)

    normalized = await provider.sync_models()

    assert len(normalized) == 2
    first = normalized[0]
    assert first["model_id"] == "Poe-Text-Tools"
    assert first["provider_model_id"] == "poe-text-tools"
    assert first["modality"] == "text"
    assert first["endpoint_type"] == "chat_completions"
    assert first["capabilities"]["supports_tools"] is True
    assert first["constraints"]["context_length"] == 200000
    assert first["cost_config"]["compute_points"] == 15

    second = normalized[1]
    assert second["modality"] == "video"
    assert second["endpoint_type"] == "generateVideo"
    assert second["capabilities"]["supports_tools"] is False

    listed = await provider.list_models()
    assert listed == raw_models

    assert provider.supports_tools("Poe-Video-NoTools") is False
    assert provider.supports_tools("Poe-Text-Tools") is True


def test_classify_error_maps_poe_specific_errors() -> None:
    provider = PoeProvider(uuid4(), {"api_key": "test-key"})

    assert isinstance(provider.classify_error(Exception("engine overloaded")), ProviderOverloadedError)
    assert isinstance(provider.classify_error(Exception("HTTP 429 Too Many Requests")), ProviderRateLimitError)
    assert isinstance(provider.classify_error(httpx.ConnectError("network down")), ProviderConnectionError)
    assert isinstance(provider.classify_error(httpx.ReadTimeout("request timed out")), ProviderTimeoutError)
    assert isinstance(provider.classify_error(Exception("unknown boom")), ProviderError)


# ---------------------------------------------------------------------------
# Normalization unit tests (migrated from test_model_normalizer)
# ---------------------------------------------------------------------------


class TestPoeNormalization:
    def test_image_output_modality_maps_to_generate_image_endpoint(self) -> None:
        result = PoeProvider._normalize_poe_model({
            "id": "flux-schnell",
            "root": "flux-schnell-v1",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["image"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {"display_name": "Flux Schnell"},
        })
        assert result["modality"] == "image"
        assert result["endpoint_type"] == "generateImage"
        assert result["model_id"] == "flux-schnell"
        assert result["provider_model_id"] == "flux-schnell-v1"
        assert result["display_name"] == "Flux Schnell"
        caps = result["capabilities"]
        assert caps["outputs_image"] is True
        assert caps["outputs_text"] is False
        assert caps["outputs_video"] is False

    def test_text_output_modality_maps_to_chat_endpoint_with_features(self) -> None:
        result = PoeProvider._normalize_poe_model({
            "id": "glm-5.1",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "supported_features": ["tools", "web_search"],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        caps = result["capabilities"]
        assert caps["outputs_text"] is True
        assert caps["accepts_text"] is True
        assert caps["supports_tools"] is True
        assert caps["supports_web_search"] is True

    def test_multimodal_output_prioritizes_video_over_image_over_text(self) -> None:
        result = PoeProvider._normalize_poe_model({
            "id": "multimodal-bot",
            "architecture": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text", "image", "video"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["modality"] == "video"
        assert result["endpoint_type"] == "generateVideo"
        caps = result["capabilities"]
        assert caps["outputs_text"] is True
        assert caps["outputs_image"] is True
        assert caps["outputs_video"] is True
        assert caps["accepts_text"] is True
        assert caps["accepts_image"] is True

    def test_image_prioritized_over_text_for_modality(self) -> None:
        result = PoeProvider._normalize_poe_model({
            "id": "image-chat",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text", "image"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["modality"] == "image"
        assert result["endpoint_type"] == "generateImage"

    def test_v1_images_endpoint_forces_generate_image(self) -> None:
        result = PoeProvider._normalize_poe_model({
            "id": "img-api-bot",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["image", "text"],
            },
            "supported_features": [],
            "supported_endpoints": ["/v1/images", "/v1/chat/completions"],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["endpoint_type"] == "generateImage"

    def test_minimal_data_does_not_crash(self) -> None:
        result = PoeProvider._normalize_poe_model({
            "id": "minimal-bot",
            "architecture": {},
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["model_id"] == "minimal-bot"
        assert result["provider_model_id"] == "minimal-bot"
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        caps = result["capabilities"]
        assert caps["outputs_text"] is False
        assert caps["outputs_image"] is False
        assert caps["outputs_video"] is False
        assert caps["supports_tools"] is False

    def test_missing_optional_fields_does_not_crash(self) -> None:
        result = PoeProvider._normalize_poe_model({
            "id": "no-extras",
            "architecture": {
                "input_modalities": [],
                "output_modalities": ["text"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "metadata": {},
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert "cost_config" not in result
        assert "constraints" not in result
