import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from unittest.mock import AsyncMock

from app.services.providers.atlascloud import AtlasCloudProvider
from app.services.providers.base import (
    ProviderConnectionError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        json_data: dict[str, Any] | None = None,
        content: bytes = b"",
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.content = content
        self._text = text

    def json(self) -> dict[str, Any]:
        return self._json_data

    async def aread(self) -> bytes:
        if self._text:
            return self._text.encode("utf-8")
        return json.dumps(self._json_data).encode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://test.local")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("status error", request=request, response=response)


class FakeAtlasClient:
    def __init__(
        self,
        *,
        poll_results: list[dict[str, Any]] | None = None,
        assets: dict[str, bytes] | None = None,
        models: list[dict[str, Any]] | None = None,
    ) -> None:
        self.poll_results = list(poll_results or [])
        self.assets = assets or {}
        self.models = models or []
        self.calls: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        if url.endswith("/model/generateImage"):
            return FakeResponse(
                200,
                {"data": {"id": "img-pred-1", "urls": {"get": "https://atlas.test/getResult"}}},
            )
        if url.endswith("/model/generateVideo"):
            return FakeResponse(
                200,
                {"data": {"id": "vid-pred-1", "urls": {"get": "https://atlas.test/getResult"}}},
            )
        if url.endswith("/model/uploadMedia"):
            return FakeResponse(200, {"data": {"download_url": "https://cdn.test/uploaded.png"}})
        return FakeResponse(404, {"message": "not found"})

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append(
            {
                "method": "GET",
                "url": url,
                "params": params,
                "headers": headers,
            }
        )
        if url.endswith("/models"):
            return FakeResponse(200, {"data": self.models})
        if "getResult" in url:
            if self.poll_results:
                return FakeResponse(200, self.poll_results.pop(0))
            return FakeResponse(200, {"data": {"status": "failed", "error": "missing poll response"}})
        if url in self.assets:
            return FakeResponse(200, content=self.assets[url])
        return FakeResponse(404, {"message": "asset not found"})


class FakeModelConfig:
    def __init__(self, provider_model_id: str) -> None:
        self.provider_model_id = provider_model_id
        self.constraints: dict[str, Any] = {}
        self.parameter_map: dict[str, str] = {}

    def build_payload(self, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"prompt": kwargs.get("prompt", "")}
        if kwargs.get("duration") is not None:
            payload["duration"] = kwargs["duration"]
        if kwargs.get("aspect_ratio") is not None:
            payload["aspect_ratio"] = kwargs["aspect_ratio"]
        if kwargs.get("image_url") is not None:
            payload["image_url"] = kwargs["image_url"]
        return payload


def _provider_with_client(client: FakeAtlasClient) -> AtlasCloudProvider:
    provider = AtlasCloudProvider(provider_id=uuid4(), config={"api_key": "test-token"})
    provider.client = client  # type: ignore[assignment]
    return provider


def test_get_capabilities_declares_image_video_llm_and_sync() -> None:
    provider = AtlasCloudProvider(provider_id=uuid4(), config={"api_key": "test-token"})
    caps = provider.get_capabilities()

    assert caps.supports_image is True
    assert caps.supports_video is True
    assert caps.supports_llm is True
    assert caps.supports_model_sync is True


@pytest.mark.asyncio
async def test_generate_image_wraps_atlas_async_api(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.services.providers.atlascloud.asyncio.sleep", _no_sleep)

    image_url = "https://cdn.test/generated-image.png"
    client = FakeAtlasClient(
        poll_results=[{"data": {"status": "completed", "url": image_url}}],
        assets={image_url: b"image-bytes"},
    )
    provider = _provider_with_client(client)
    provider._get_model_config = AsyncMock(return_value=FakeModelConfig("atlas/flux/text-to-image"))

    model_id, data = await provider.generate_image(
        prompt="city skyline at sunset",
        model="atlas/flux/text-to-image",
        aspect_ratio="16:9",
    )

    assert model_id == "atlas/flux/text-to-image"
    assert data == b"image-bytes"
    assert any(call["url"].endswith("/model/generateImage") for call in client.calls)


@pytest.mark.asyncio
async def test_generate_video_wraps_atlas_async_api_with_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.services.providers.atlascloud.asyncio.sleep", _no_sleep)

    video_url = "https://cdn.test/generated-video.mp4"
    client = FakeAtlasClient(
        poll_results=[
            {"data": {"status": "processing"}},
            {"data": {"status": "completed", "url": video_url}},
        ],
        assets={video_url: b"video-bytes"},
    )
    provider = _provider_with_client(client)
    provider._get_model_config = AsyncMock(return_value=FakeModelConfig("atlas/wan/text-to-video"))

    model_id, data = await provider.generate_video(
        prompt="flying over mountains",
        model="atlas/wan/text-to-video",
        duration=5,
        aspect_ratio="16:9",
    )

    assert model_id == "atlas/wan/text-to-video"
    assert data == b"video-bytes"
    assert any(call["url"].endswith("/model/generateVideo") for call in client.calls)


@pytest.mark.asyncio
async def test_sync_models_normalizes_atlascloud_models() -> None:
    raw_models = [
        {
            "model": "atlas/flux/text-to-image",
            "type": "Image",
            "displayName": "Atlas Flux",
        },
        {
            "model": "atlas/wan/image-to-video",
            "type": "Video",
            "displayName": "Atlas Wan I2V",
        },
        {
            "model": "atlas/qwen/chat",
            "type": "Text",
            "displayName": "Atlas Chat",
        },
    ]
    provider = _provider_with_client(FakeAtlasClient(models=raw_models))

    normalized = await provider.sync_models()
    listed = await provider.list_models()

    assert len(normalized) == 3
    assert listed == normalized

    by_model = {entry["model_id"]: entry for entry in normalized}

    assert by_model["atlas/flux/text-to-image"]["modality"] == "image"
    assert by_model["atlas/flux/text-to-image"]["endpoint_type"] == "generateImage"
    assert by_model["atlas/flux/text-to-image"]["capabilities"]["outputs_image"] is True

    assert by_model["atlas/wan/image-to-video"]["modality"] == "video"
    assert by_model["atlas/wan/image-to-video"]["endpoint_type"] == "generateVideo"
    assert by_model["atlas/wan/image-to-video"]["capabilities"]["accepts_image"] is True
    assert by_model["atlas/wan/image-to-video"]["capabilities"]["outputs_video"] is True

    assert by_model["atlas/qwen/chat"]["modality"] == "text"
    assert by_model["atlas/qwen/chat"]["endpoint_type"] == "chat_completions"
    assert by_model["atlas/qwen/chat"]["capabilities"]["supports_chat"] is True


def test_classify_error_maps_provider_specific_patterns() -> None:
    provider = AtlasCloudProvider(provider_id=uuid4(), config={"api_key": "test-token"})

    assert isinstance(provider.classify_error(Exception("Queue is full right now")), ProviderOverloadedError)
    assert isinstance(provider.classify_error(Exception("HTTP 429 Too Many Requests")), ProviderRateLimitError)
    assert isinstance(provider.classify_error(Exception("request timed out")), ProviderTimeoutError)
    assert isinstance(provider.classify_error(Exception("connection reset by peer")), ProviderConnectionError)


# ---------------------------------------------------------------------------
# Normalization unit tests (migrated from test_model_normalizer)
# ---------------------------------------------------------------------------


class TestAtlasCloudNormalization:
    def test_image_type_maps_to_image_modality_and_generate_endpoint(self) -> None:
        result = AtlasCloudProvider._normalize_model({
            "model": "flux-schnell",
            "type": "Image",
            "displayName": "Flux Schnell",
        })
        assert result["modality"] == "image"
        assert result["endpoint_type"] == "generateImage"
        assert result["model_id"] == "flux-schnell"
        assert result["provider_model_id"] == "flux-schnell"
        assert result["display_name"] == "Flux Schnell"
        assert not result["capabilities"]["supports_chat"]

    def test_video_type_maps_to_video_modality_and_generate_endpoint(self) -> None:
        result = AtlasCloudProvider._normalize_model({
            "model": "wan-2.2",
            "type": "Video",
            "displayName": "Wan 2.2",
        })
        assert result["modality"] == "video"
        assert result["endpoint_type"] == "generateVideo"
        assert not result["capabilities"]["supports_chat"]

    def test_text_type_maps_to_text_modality_and_chat_endpoint(self) -> None:
        result = AtlasCloudProvider._normalize_model({
            "model": "llama-3.3",
            "type": "Text",
            "displayName": "Llama 3.3",
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert result["capabilities"]["supports_chat"] is True

    def test_without_type_defaults_to_text(self) -> None:
        result = AtlasCloudProvider._normalize_model({
            "model": "some-model",
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert result["capabilities"]["supports_chat"] is True

    def test_minimal_data_does_not_crash(self) -> None:
        result = AtlasCloudProvider._normalize_model({
            "model": "bare-minimum",
        })
        assert result["model_id"] == "bare-minimum"
        assert result["display_name"] == "bare-minimum"
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert result["cost_config"] == {"currency": "credits"}
