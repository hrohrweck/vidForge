"""Unit tests for RunPodProvider implementing ImageProvider + VideoProvider.

Covers:
- Capability declarations (supports_image, supports_video, etc.)
- generate_video with mocked RunPod API (queue, poll, output)
- generate_image with mocked RunPod API
- Cost tracking (estimate_cost, estimate_duration, cost_per_gpu_hour)
- Error classification (RunPod-specific + inherited patterns)
- sync_models and list_models
- MRO and interface compliance
"""

from __future__ import annotations

import base64
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.providers.base import (
    ComfyUIProvider,
    ImageProvider,
    ProviderCapabilities,
    ProviderConnectionError,
    ProviderError,
    ProviderOverloadedError,
    ProviderTimeoutError,
    VideoProvider,
)
from app.services.providers.runpod import RunPodProvider


def _make_provider(config: dict | None = None) -> RunPodProvider:
    base_config = {
        "endpoint_id": "test-endpoint-123",
        "api_key": "test-api-key",
        "cost_per_gpu_hour": 0.69,
    }
    if config:
        base_config.update(config)
    return RunPodProvider(provider_id=uuid4(), config=base_config)


class TestInterfaceCompliance:
    def test_inherits_comfyui_provider(self):
        provider = _make_provider()
        assert isinstance(provider, ComfyUIProvider)

    def test_inherits_image_provider(self):
        provider = _make_provider()
        assert isinstance(provider, ImageProvider)

    def test_inherits_video_provider(self):
        provider = _make_provider()
        assert isinstance(provider, VideoProvider)


class TestCapabilities:
    def test_supports_image(self):
        caps = _make_provider().get_capabilities()
        assert caps.supports_image is True

    def test_supports_video(self):
        caps = _make_provider().get_capabilities()
        assert caps.supports_video is True

    def test_does_not_support_llm(self):
        caps = _make_provider().get_capabilities()
        assert caps.supports_llm is False

    def test_supports_model_sync(self):
        caps = _make_provider().get_capabilities()
        assert caps.supports_model_sync is True

    def test_capabilities_are_frozen(self):
        caps = _make_provider().get_capabilities()
        assert isinstance(caps, ProviderCapabilities)
        with pytest.raises(AttributeError):
            caps.supports_image = False  # type: ignore[misc]


class TestGenerateVideo:
    @pytest.mark.asyncio
    async def test_generate_video_returns_model_and_bytes(self):
        provider = _make_provider()
        fake_video = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
        encoded = base64.b64encode(fake_video).decode()

        provider.queue_prompt = AsyncMock(return_value="run-abc")
        provider.wait_for_completion = AsyncMock(
            return_value={"videos": [{"video": encoded}]}
        )
        provider.get_output = AsyncMock(return_value=fake_video)

        model, data = await provider.generate_video(
            prompt="a cat walking",
            model="wan2.2",
            duration=5,
            aspect_ratio="16:9",
        )

        assert model == "wan2.2"
        assert data == fake_video
        provider.queue_prompt.assert_called_once()
        provider.wait_for_completion.assert_called_once_with(
            "run-abc", progress_callback=None
        )

    @pytest.mark.asyncio
    async def test_generate_video_passes_progress_callback(self):
        provider = _make_provider()
        provider.queue_prompt = AsyncMock(return_value="run-xyz")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=b"video-data")

        cb = AsyncMock()
        await provider.generate_video(
            prompt="test", model="wan2.2", duration=3, aspect_ratio="16:9",
            progress_callback=cb,
        )

        provider.wait_for_completion.assert_called_once_with(
            "run-xyz", progress_callback=cb
        )

    @pytest.mark.asyncio
    async def test_generate_video_raises_on_no_output(self):
        provider = _make_provider()
        provider.queue_prompt = AsyncMock(return_value="run-fail")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="no video data"):
            await provider.generate_video(
                prompt="test", model="wan2.2", duration=5, aspect_ratio="16:9"
            )

    @pytest.mark.asyncio
    async def test_generate_video_uses_config_fps(self):
        provider = _make_provider({"wan_video_fps": 24})
        provider.queue_prompt = AsyncMock(return_value="run-fps")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=b"data")

        await provider.generate_video(
            prompt="test", model="wan2.2", duration=2, aspect_ratio="16:9"
        )

        workflow = provider.queue_prompt.call_args[0][0]
        k_sampler = None
        for node in workflow.values():
            if node.get("class_type") == "EmptyHunyuanLatentVideo":
                assert node["inputs"]["length"] == 49  # 2*24=48, +1 for odd
                break


class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_generate_image_returns_model_and_bytes(self):
        provider = _make_provider()
        fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        encoded = base64.b64encode(fake_image).decode()

        provider.queue_prompt = AsyncMock(return_value="run-img-1")
        provider.wait_for_completion = AsyncMock(
            return_value={"images": [{"image": encoded}]}
        )
        provider.get_output = AsyncMock(return_value=fake_image)

        model, data = await provider.generate_image(
            prompt="a sunset", model="flux1-schnell", aspect_ratio="1:1"
        )

        assert model == "flux1-schnell"
        assert data == fake_image
        provider.queue_prompt.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_image_raises_on_no_output(self):
        provider = _make_provider()
        provider.queue_prompt = AsyncMock(return_value="run-img-fail")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="no image data"):
            await provider.generate_image(
                prompt="test", model="flux1-schnell", aspect_ratio="16:9"
            )

    @pytest.mark.asyncio
    async def test_generate_image_workflow_has_flux_nodes(self):
        provider = _make_provider()
        provider.queue_prompt = AsyncMock(return_value="run-wf")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=b"img")

        await provider.generate_image(
            prompt="hello", model="flux1-schnell", aspect_ratio="16:9"
        )

        workflow = provider.queue_prompt.call_args[0][0]
        class_types = {n["class_type"] for n in workflow.values()}
        assert "UNETLoader" in class_types
        assert "DualCLIPLoader" in class_types
        assert "VAELoader" in class_types
        assert "KSampler" in class_types
        assert "SaveImage" in class_types

    @pytest.mark.asyncio
    async def test_generate_image_uses_custom_config(self):
        provider = _make_provider({
            "flux_unet_name": "custom-unet.safetensors",
            "flux_clip_name1": "custom-clip1.safetensors",
        })
        provider.queue_prompt = AsyncMock(return_value="run-cfg")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=b"img")

        await provider.generate_image(
            prompt="test", model="flux1-schnell", aspect_ratio="16:9"
        )

        workflow = provider.queue_prompt.call_args[0][0]
        assert workflow["1"]["inputs"]["unet_name"] == "custom-unet.safetensors"
        assert workflow["2"]["inputs"]["clip_name1"] == "custom-clip1.safetensors"


class TestCostTracking:
    @pytest.mark.asyncio
    async def test_estimate_cost_uses_gpu_hour_rate(self):
        provider = _make_provider({"cost_per_gpu_hour": 1.00})
        workflow: dict = {}
        cost = await provider.estimate_cost(workflow)
        expected_seconds = 30.0
        expected_cost = (Decimal("1.00") / 3600) * Decimal(str(expected_seconds))
        assert abs(cost - float(expected_cost)) < 1e-6

    @pytest.mark.asyncio
    async def test_estimate_duration_base(self):
        provider = _make_provider()
        duration = await provider.estimate_duration({})
        assert duration == 30.0

    @pytest.mark.asyncio
    async def test_estimate_duration_adds_for_video_steps(self):
        provider = _make_provider()
        workflow = {"pipeline": [{"step": "generate_video"}]}
        duration = await provider.estimate_duration(workflow)
        assert duration == 75.0

    @pytest.mark.asyncio
    async def test_estimate_duration_caps_at_600(self):
        provider = _make_provider()
        pipeline = [{"step": "generate_video"}] * 20
        duration = await provider.estimate_duration({"pipeline": pipeline})
        assert duration == 600.0

    def test_cost_per_gpu_hour_from_config(self):
        provider = _make_provider({"cost_per_gpu_hour": 2.50})
        assert provider.cost_per_gpu_hour == Decimal("2.50")

    def test_cost_per_gpu_hour_default(self):
        provider = RunPodProvider(provider_id=uuid4(), config={})
        assert provider.cost_per_gpu_hour == Decimal("0.69")


class TestErrorClassification:
    def test_cold_start_maps_to_timeout(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("cold start detected"))
        assert isinstance(err, ProviderTimeoutError)

    def test_runpod_job_failed_maps_to_provider_error(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("RunPod job failed: OOM"))
        assert isinstance(err, ProviderError)

    def test_runpod_api_error_maps_to_connection(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("RunPod API error 500"))
        assert isinstance(err, ProviderConnectionError)

    def test_overloaded_maps_to_overloaded(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("Server is overloaded"))
        assert isinstance(err, ProviderOverloadedError)

    def test_queue_full_maps_to_overloaded(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("queue is full"))
        assert isinstance(err, ProviderOverloadedError)

    def test_timeout_maps_to_timeout(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("Request timed out"))
        assert isinstance(err, ProviderTimeoutError)

    def test_unknown_error_maps_to_base_provider_error(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("something completely unexpected"))
        assert isinstance(err, ProviderError)
        assert not isinstance(err, (ProviderTimeoutError, ProviderOverloadedError))

    def test_cancelled_maps_to_provider_error(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("RunPod job was cancelled"))
        assert isinstance(err, ProviderError)

    def test_endpoint_not_found_maps_to_connection(self):
        provider = _make_provider()
        err = provider.classify_error(Exception("endpoint not found"))
        assert isinstance(err, ProviderConnectionError)


class TestModelSync:
    @pytest.mark.asyncio
    async def test_list_models_returns_defaults(self):
        provider = _make_provider()
        models = await provider.list_models()
        assert len(models) == 2
        ids = {m["id"] for m in models}
        assert "wan2.2" in ids
        assert "flux1-schnell" in ids

    @pytest.mark.asyncio
    async def test_list_models_includes_type(self):
        provider = _make_provider()
        models = await provider.list_models()
        types = {m["id"]: m["type"] for m in models}
        assert types["wan2.2"] == "video"
        assert types["flux1-schnell"] == "image"

    @pytest.mark.asyncio
    async def test_sync_models_returns_models(self):
        provider = _make_provider()
        provider.get_endpoint_info = AsyncMock(return_value={})
        models = await provider.sync_models()
        assert len(models) == 2

    @pytest.mark.asyncio
    async def test_sync_models_marks_endpoint_available(self):
        provider = _make_provider()
        provider.get_endpoint_info = AsyncMock(
            return_value={"status": "RUNNING"}
        )
        models = await provider.sync_models()
        for m in models:
            assert m["endpoint_available"] is True

    @pytest.mark.asyncio
    async def test_sync_models_marks_endpoint_unavailable(self):
        provider = _make_provider()
        provider.get_endpoint_info = AsyncMock(
            return_value={"status": "IDLE"}
        )
        models = await provider.sync_models()
        for m in models:
            assert m["endpoint_available"] is False


class TestImageResolution:
    def test_16_9(self):
        assert RunPodProvider._image_resolution("16:9") == (1280, 720)

    def test_9_16(self):
        assert RunPodProvider._image_resolution("9:16") == (720, 1280)

    def test_1_1(self):
        assert RunPodProvider._image_resolution("1:1") == (1024, 1024)

    def test_unknown_defaults_to_16_9(self):
        assert RunPodProvider._image_resolution("32:9") == (1280, 720)


class TestBackwardCompat:
    @pytest.mark.asyncio
    async def test_queue_prompt_still_works(self):
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "job-123"}
        mock_client.post = AsyncMock(return_value=mock_response)
        provider.client = mock_client

        result = await provider.queue_prompt({"test": "workflow"})
        assert result == "job-123"

    @pytest.mark.asyncio
    async def test_get_output_extracts_video(self):
        provider = _make_provider()
        fake_data = b"video-bytes"
        encoded = base64.b64encode(fake_data).decode()
        result = await provider.get_output({"videos": [{"video": encoded}]})
        assert result == fake_data

    @pytest.mark.asyncio
    async def test_get_output_extracts_image(self):
        provider = _make_provider()
        fake_data = b"image-bytes"
        encoded = base64.b64encode(fake_data).decode()
        result = await provider.get_output({"images": [{"image": encoded}]})
        assert result == fake_data

    @pytest.mark.asyncio
    async def test_get_output_returns_none_for_empty(self):
        provider = _make_provider()
        result = await provider.get_output({})
        assert result is None

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self):
        provider = _make_provider()
        mock_client = AsyncMock()
        provider.client = mock_client
        await provider.shutdown()
        mock_client.aclose.assert_called_once()
        assert provider.client is None
