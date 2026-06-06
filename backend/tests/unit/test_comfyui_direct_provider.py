from __future__ import annotations

from typing import Any
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
from app.services.providers.comfyui_direct import (
    ComfyUIDirectProvider,
    _duration_to_frames,
)


@pytest.fixture
def provider() -> ComfyUIDirectProvider:
    return ComfyUIDirectProvider(provider_id=uuid4(), config={"comfyui_url": "http://localhost:8188"})


class TestInheritance:
    def test_is_image_provider(self, provider: ComfyUIDirectProvider) -> None:
        assert isinstance(provider, ImageProvider)

    def test_is_video_provider(self, provider: ComfyUIDirectProvider) -> None:
        assert isinstance(provider, VideoProvider)

    def test_is_comfyui_provider(self, provider: ComfyUIDirectProvider) -> None:
        assert isinstance(provider, ComfyUIProvider)


class TestCapabilities:
    def test_supports_image(self, provider: ComfyUIDirectProvider) -> None:
        caps = provider.get_capabilities()
        assert caps.supports_image is True

    def test_supports_video(self, provider: ComfyUIDirectProvider) -> None:
        caps = provider.get_capabilities()
        assert caps.supports_video is True

    def test_does_not_support_llm(self, provider: ComfyUIDirectProvider) -> None:
        caps = provider.get_capabilities()
        assert caps.supports_llm is False

    def test_supports_model_sync(self, provider: ComfyUIDirectProvider) -> None:
        caps = provider.get_capabilities()
        assert caps.supports_model_sync is True

    def test_capabilities_frozen(self, provider: ComfyUIDirectProvider) -> None:
        caps = provider.get_capabilities()
        with pytest.raises(Exception):
            caps.supports_image = False  # type: ignore[misc]


class TestDurationToFrames:
    def test_basic_conversion(self) -> None:
        frames = _duration_to_frames(5, fps=16)
        assert frames == 81

    def test_minimum_frames(self) -> None:
        frames = _duration_to_frames(0, fps=16)
        assert frames >= 9

    def test_odd_frame_count(self) -> None:
        frames = _duration_to_frames(2, fps=16)
        assert frames % 2 == 1

    def test_short_duration(self) -> None:
        frames = _duration_to_frames(1, fps=16)
        assert frames >= 9
        assert frames % 2 == 1


class TestClassifyError:
    def test_overloaded_error(self, provider: ComfyUIDirectProvider) -> None:
        result = provider.classify_error(Exception("Server is overloaded"))
        assert isinstance(result, ProviderOverloadedError)

    def test_timeout_error(self, provider: ComfyUIDirectProvider) -> None:
        result = provider.classify_error(Exception("Operation timed out"))
        assert isinstance(result, ProviderTimeoutError)

    def test_connection_error(self, provider: ComfyUIDirectProvider) -> None:
        result = provider.classify_error(Exception("Connection refused"))
        assert isinstance(result, ProviderConnectionError)

    def test_did_not_complete_timeout(self, provider: ComfyUIDirectProvider) -> None:
        result = provider.classify_error(Exception("Job did not complete within 300s"))
        assert isinstance(result, ProviderTimeoutError)

    def test_generic_error(self, provider: ComfyUIDirectProvider) -> None:
        result = provider.classify_error(Exception("Something unexpected happened"))
        assert isinstance(result, ProviderError)
        assert not isinstance(result, ProviderOverloadedError)
        assert not isinstance(result, ProviderTimeoutError)
        assert not isinstance(result, ProviderConnectionError)

    def test_queue_full_error(self, provider: ComfyUIDirectProvider) -> None:
        result = provider.classify_error(Exception("queue is full"))
        assert isinstance(result, ProviderOverloadedError)


class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_raises_when_not_initialized(self, provider: ComfyUIDirectProvider) -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            await provider.generate_image("test prompt", "flux1-schnell", "16:9")

    @pytest.mark.asyncio
    async def test_flux_model_uses_flux_workflow(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = AsyncMock()
        provider.client = mock_client

        mock_client.queue_prompt.return_value = {"prompt_id": "test-prompt-id"}
        mock_client.get_history.return_value = {
            "test-prompt-id": {
                "status": {"completed": True},
                "outputs": {"9": {"images": [{"filename": "test.png", "subfolder": "", "type": "output"}]}},
            }
        }
        mock_client.get_output.return_value = b"fake-image-data"
        mock_client.get_video_output.return_value = b"fake-image-data"

        model, image_bytes = await provider.generate_image(
            "a beautiful sunset", "flux1-schnell", "16:9"
        )

        assert model == "flux1-schnell"
        assert image_bytes == b"fake-image-data"
        mock_client.queue_prompt.assert_called_once()
        workflow = mock_client.queue_prompt.call_args[0][0]
        assert any(
            node.get("class_type") == "UNETLoader"
            for node in workflow.values()
        )

    @pytest.mark.asyncio
    async def test_wan_model_uses_comfyui_workflow(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = AsyncMock()
        provider.client = mock_client

        mock_client.queue_prompt.return_value = {"prompt_id": "test-prompt-id"}
        mock_client.get_history.return_value = {
            "test-prompt-id": {
                "status": {"completed": True},
                "outputs": {"10": {"images": [{"filename": "test.png", "subfolder": "", "type": "output"}]}},
            }
        }
        mock_client.get_output.return_value = b"fake-image-data"
        mock_client.get_video_output.return_value = b"fake-image-data"

        model, image_bytes = await provider.generate_image(
            "a cat", "wan2.2-ti2v", "1:1"
        )

        assert model == "wan2.2-ti2v"
        assert image_bytes == b"fake-image-data"

    @pytest.mark.asyncio
    async def test_raises_on_empty_output(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = AsyncMock()
        provider.client = mock_client

        mock_client.queue_prompt.return_value = {"prompt_id": "test-prompt-id"}
        mock_client.get_history.return_value = {
            "test-prompt-id": {
                "status": {"completed": True},
                "outputs": {},
            }
        }
        mock_client.get_video_output.return_value = None

        with pytest.raises(ValueError, match="no output data"):
            await provider.generate_image("test", "flux1-schnell", "16:9")


class TestGenerateVideo:
    @pytest.mark.asyncio
    async def test_raises_when_not_initialized(self, provider: ComfyUIDirectProvider) -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            await provider.generate_video("test prompt", "wan2.2", 5, "16:9")

    @pytest.mark.asyncio
    async def test_wan_model_uses_wan_workflow(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = AsyncMock()
        provider.client = mock_client

        mock_client.queue_prompt.return_value = {"prompt_id": "test-prompt-id"}
        mock_client.get_history.return_value = {
            "test-prompt-id": {
                "status": {"completed": True},
                "outputs": {"11": {"videos": [{"filename": "test.mp4", "subfolder": "", "type": "output"}]}},
            }
        }
        mock_client.get_video_output.return_value = b"fake-video-data"

        model, video_bytes = await provider.generate_video(
            "a flying bird", "wan2.2", 5, "16:9"
        )

        assert model == "wan2.2"
        assert video_bytes == b"fake-video-data"
        mock_client.queue_prompt.assert_called_once()
        workflow = mock_client.queue_prompt.call_args[0][0]
        assert any(
            node.get("class_type") == "KSampler"
            for node in workflow.values()
        )

    @pytest.mark.asyncio
    async def test_unsupported_model_raises(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = AsyncMock()
        provider.client = mock_client

        with pytest.raises(ValueError, match="Unsupported model variant"):
            await provider.generate_video("test", "sdxl-turbo", 5, "16:9")

    @pytest.mark.asyncio
    async def test_raises_on_empty_output(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = AsyncMock()
        provider.client = mock_client

        mock_client.queue_prompt.return_value = {"prompt_id": "test-prompt-id"}
        mock_client.get_history.return_value = {
            "test-prompt-id": {
                "status": {"completed": True},
                "outputs": {},
            }
        }
        mock_client.get_video_output.return_value = None

        with pytest.raises(ValueError, match="no output data"):
            await provider.generate_video("test", "wan2.2", 5, "16:9")

    @pytest.mark.asyncio
    async def test_wan_with_reference_image_uploads_and_uses_i2v(
        self, provider: ComfyUIDirectProvider, tmp_path: Any
    ) -> None:
        mock_client = AsyncMock()
        provider.client = mock_client

        ref_image = tmp_path / "seed.png"
        ref_image.write_bytes(b"fake-png-data")

        mock_client.upload_file.return_value = "seed.png"
        mock_client.queue_prompt.return_value = {"prompt_id": "test-prompt-id"}
        mock_client.get_history.return_value = {
            "test-prompt-id": {
                "status": {"completed": True},
                "outputs": {"12": {"videos": [{"filename": "test.mp4", "subfolder": "", "type": "output"}]}},
            }
        }
        mock_client.get_video_output.return_value = b"fake-video-data"

        model, video_bytes = await provider.generate_video(
            "a flying bird",
            "wan2.2",
            5,
            "16:9",
            reference_image_path="seed.png",
            storage_path=str(tmp_path),
        )

        assert model == "wan2.2"
        assert video_bytes == b"fake-video-data"
        mock_client.upload_file.assert_called_once()
        workflow = mock_client.queue_prompt.call_args[0][0]
        assert any(
            node.get("class_type") == "WanImageToVideo"
            for node in workflow.values()
        )


class TestSyncModels:
    @pytest.mark.asyncio
    async def test_raises_when_not_initialized(self, provider: ComfyUIDirectProvider) -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            await provider.sync_models()

    @pytest.mark.asyncio
    async def test_fetches_unet_clip_vae_models(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = MagicMock()
        mock_http = AsyncMock()
        mock_client.client = mock_http
        mock_client.base_url = "http://localhost:8188"
        provider.client = mock_client

        def make_response(data: dict) -> MagicMock:
            resp = MagicMock()
            resp.json.return_value = data
            resp.raise_for_status = MagicMock()
            return resp

        unet_response = make_response({
            "UNETLoader": {
                "input": {
                    "required": {
                        "unet_name": [["wan2.2_ti2v_5B_fp16.safetensors", "flux1-schnell-fp8.safetensors"]]
                    }
                }
            }
        })
        clip_response = make_response({
            "CLIPLoader": {
                "input": {
                    "required": {
                        "clip_name": [["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]]
                    }
                }
            }
        })
        vae_response = make_response({
            "VAELoader": {
                "input": {
                    "required": {
                        "vae_name": [["wan2.2_vae.safetensors", "ae.safetensors"]]
                    }
                }
            }
        })

        mock_http.get = AsyncMock(side_effect=[unet_response, clip_response, vae_response])

        models = await provider.sync_models()

        assert len(models) == 5
        unet_models = [m for m in models if m["category"] == "unet"]
        assert len(unet_models) == 2
        assert unet_models[0]["name"] == "wan2.2_ti2v_5B_fp16.safetensors"
        assert unet_models[0]["type"] == "video"
        assert unet_models[1]["name"] == "flux1-schnell-fp8.safetensors"
        assert unet_models[1]["type"] == "image"

        clip_models = [m for m in models if m["category"] == "clip"]
        assert len(clip_models) == 1

        vae_models = [m for m in models if m["category"] == "vae"]
        assert len(vae_models) == 2

    @pytest.mark.asyncio
    async def test_handles_api_failure_gracefully(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = MagicMock()
        mock_http = AsyncMock()
        mock_client.client = mock_http
        mock_client.base_url = "http://localhost:8188"
        provider.client = mock_client

        mock_http.get = AsyncMock(side_effect=Exception("Connection refused"))

        models = await provider.sync_models()
        assert models == []


class TestListModels:
    @pytest.mark.asyncio
    async def test_delegates_to_sync_models(self, provider: ComfyUIDirectProvider) -> None:
        mock_client = MagicMock()
        mock_http = AsyncMock()
        mock_client.client = mock_http
        mock_client.base_url = "http://localhost:8188"
        provider.client = mock_client

        def make_response(data: dict) -> MagicMock:
            resp = MagicMock()
            resp.json.return_value = data
            resp.raise_for_status = MagicMock()
            return resp

        empty_response = make_response({
            "UNETLoader": {"input": {"required": {"unet_name": [[]]}}},
        })
        mock_http.get = AsyncMock(return_value=empty_response)

        models = await provider.list_models()
        assert isinstance(models, list)


class TestBackwardCompat:
    def test_has_queue_prompt(self, provider: ComfyUIDirectProvider) -> None:
        assert hasattr(provider, "queue_prompt")
        assert callable(provider.queue_prompt)

    def test_has_wait_for_completion(self, provider: ComfyUIDirectProvider) -> None:
        assert hasattr(provider, "wait_for_completion")
        assert callable(provider.wait_for_completion)

    def test_has_get_output(self, provider: ComfyUIDirectProvider) -> None:
        assert hasattr(provider, "get_output")
        assert callable(provider.get_output)

    def test_has_cancel_job(self, provider: ComfyUIDirectProvider) -> None:
        assert hasattr(provider, "cancel_job")
        assert callable(provider.cancel_job)

    def test_has_estimate_cost(self, provider: ComfyUIDirectProvider) -> None:
        assert hasattr(provider, "estimate_cost")

    def test_has_estimate_duration(self, provider: ComfyUIDirectProvider) -> None:
        assert hasattr(provider, "estimate_duration")
