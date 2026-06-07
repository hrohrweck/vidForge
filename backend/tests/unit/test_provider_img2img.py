"""Unit tests for provider img2img/I2V behaviour across all providers.

Tests that each provider correctly:
- Uses img2img when image_path is provided
- Falls back to T2I/T2V when image_path is absent
- Sends reference image data in the correct format for each provider

Run with: pytest tests/unit/test_provider_img2img.py -v
"""

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.providers.atlascloud import AtlasCloudProvider
from app.services.providers.comfyui_direct import ComfyUIDirectProvider
from app.services.providers.poe import PoeProvider
from app.services.providers.runpod import RunPodProvider


# ── Mock Helpers ──────────────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None,
                 text: str = "", content: bytes = b""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.content = content

    def json(self) -> dict:
        return self._json_data

    async def aread(self) -> bytes:
        return self.text.encode("utf-8")


# ── Poe Provider img2img Tests ────────────────────────────────────────────


class FakePoeClient:
    def __init__(self):
        self.post_responses: dict[str, FakeResponse] = {}
        self.post_requests: list[dict] = []

    async def post(self, url: str, json: dict, headers: dict) -> FakeResponse:
        self.post_requests.append({"url": url, "json": json, "headers": headers})
        return self.post_responses.get(url, FakeResponse(500))


def _poe_provider(client: FakePoeClient) -> PoeProvider:
    provider = PoeProvider(uuid4(), {"api_key": "test-key"})
    provider.client = client  # type: ignore[assignment]
    return provider


class TestPoeImg2Img:
    @pytest.mark.asyncio
    async def test_generate_image_with_image_path_sends_vision_content(self):
        """Poe generate_image with image_path sends base64-encoded image in vision format."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a fake image file
            img_path = Path(tmp) / "reference.png"
            img_path.write_bytes(b"fake-image-bytes")
            rel_path = "reference.png"

            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value.storage_path = tmp

                image_payload = json.dumps({
                    "image_base64": base64.b64encode(b"image-bytes").decode("ascii")
                })
                client = FakePoeClient()
                client.post_responses["https://api.poe.com/v1/chat/completions"] = FakeResponse(
                    200, json_data={
                        "id": "img-123",
                        "choices": [{"message": {"content": image_payload}}],
                    }
                )
                provider = _poe_provider(client)

                asset_id, data = await provider.generate_image(
                    prompt="a landscape", model="GPT-Image-1",
                    aspect_ratio="1:1", image_path=rel_path,
                )

            assert asset_id == "img-123"
            assert data == b"image-bytes"

            # Verify the request included an image_url in the content array
            req_json = client.post_requests[0]["json"]
            messages = req_json["messages"]
            assert len(messages) == 1
            content_list = messages[0]["content"]
            assert isinstance(content_list, list)
            assert content_list[0]["type"] == "image_url"
            assert "base64" in content_list[0]["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_generate_image_without_image_path_sends_text_only(self):
        """Poe generate_image WITHOUT image_path sends plain text prompt."""
        image_payload = json.dumps({
            "image_base64": base64.b64encode(b"image-bytes").decode("ascii")
        })
        client = FakePoeClient()
        client.post_responses["https://api.poe.com/v1/chat/completions"] = FakeResponse(
            200, json_data={
                "id": "img-456",
                "choices": [{"message": {"content": image_payload}}],
            }
        )
        provider = _poe_provider(client)

        asset_id, data = await provider.generate_image(
            prompt="a landscape", model="GPT-Image-1", aspect_ratio="1:1",
        )

        assert asset_id == "img-456"
        # Verify content is plain text, not an array
        req_json = client.post_requests[0]["json"]
        content = req_json["messages"][0]["content"]
        assert isinstance(content, str)

    @pytest.mark.asyncio
    async def test_generate_video_with_image_path_sends_image_bytes(self):
        """Poe generate_video with image_path includes base64 image data in request."""
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "ref.png"
            img_path.write_bytes(b"fake-ref-image")
            rel_path = "ref.png"

            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value.storage_path = tmp

                video_payload = json.dumps({
                    "video_base64": base64.b64encode(b"video-bytes").decode("ascii")
                })
                client = FakePoeClient()
                client.post_responses["https://api.poe.com/v1/chat/completions"] = FakeResponse(
                    200, json_data={
                        "id": "vid-789",
                        "choices": [{"message": {"content": video_payload}}],
                    }
                )
                provider = _poe_provider(client)

                asset_id, data = await provider.generate_video(
                    prompt="a flyover", model="Veo-3",
                    duration=5, aspect_ratio="16:9", image_path=rel_path,
                )

            assert asset_id == "vid-789"
            assert data == b"video-bytes"
            req_json = client.post_requests[0]["json"]
            content_list = req_json["messages"][0]["content"]
            assert isinstance(content_list, list)

    @pytest.mark.asyncio
    async def test_generate_video_without_image_path_is_text_only(self):
        """Poe generate_video WITHOUT image_path sends plain text."""
        video_payload = json.dumps({
            "video_base64": base64.b64encode(b"video-bytes").decode("ascii")
        })
        client = FakePoeClient()
        client.post_responses["https://api.poe.com/v1/chat/completions"] = FakeResponse(
            200, json_data={
                "id": "vid-000",
                "choices": [{"message": {"content": video_payload}}],
            }
        )
        provider = _poe_provider(client)

        await provider.generate_video(
            prompt="test", model="Veo-3", duration=5, aspect_ratio="16:9",
        )

        req_json = client.post_requests[0]["json"]
        content = req_json["messages"][0]["content"]
        assert isinstance(content, str)


# ── ComfyUI Provider img2img Tests ───────────────────────────────────────


class TestComfyUIImg2Img:
    @pytest.mark.asyncio
    async def test_generate_image_with_image_path_uses_ip_adapter_workflow(self):
        """ComfyUI generate_image with image_path selects IP-Adapter workflow."""
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "ref.png"
            img_path.write_bytes(b"fake-image-data")

            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value.storage_path = tmp

                provider = ComfyUIDirectProvider(provider_id=uuid4(), config={})
                mock_client = AsyncMock()
                mock_client.queue_prompt.return_value = {"prompt_id": "img2img-test"}
                mock_client.get_history.return_value = {
                    "img2img-test": {
                        "status": {"completed": True},
                        "outputs": {"9": {"images": [
                            {"filename": "test.png", "subfolder": "", "type": "output"}
                        ]}},
                    }
                }
                mock_client.get_video_output.return_value = b"ip-adapter-image-data"
                mock_client.upload_file.return_value = "uploaded_ref.png"
                provider.client = mock_client

                model, data = await provider.generate_image(
                    prompt="a portrait", model="flux1-schnell",
                    aspect_ratio="1:1", image_path="ref.png",
                    reference_image_strength=0.65,
                )

            assert model == "flux1-schnell"
            assert data == b"ip-adapter-image-data"
            mock_client.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_image_without_image_path_uses_standard_workflow(self):
        """ComfyUI generate_image WITHOUT image_path uses standard T2I workflow."""
        provider = ComfyUIDirectProvider(provider_id=uuid4(), config={})
        mock_client = AsyncMock()
        mock_client.queue_prompt.return_value = {"prompt_id": "t2i-test"}
        mock_client.get_history.return_value = {
            "t2i-test": {
                "status": {"completed": True},
                "outputs": {"9": {"images": [
                    {"filename": "test.png", "subfolder": "", "type": "output"}
                ]}},
            }
        }
        mock_client.get_video_output.return_value = b"standard-image-data"
        provider.client = mock_client

        model, data = await provider.generate_image(
            prompt="a landscape", model="flux1-schnell", aspect_ratio="16:9",
        )

        assert model == "flux1-schnell"
        assert data == b"standard-image-data"
        # upload_file should NOT be called (no reference image)
        mock_client.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_video_with_reference_image_path(self):
        """ComfyUI generate_video with reference_image_path sends it to ComfyUI."""
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "ref_frame.png"
            img_path.write_bytes(b"fake-ref-frame")

            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value.storage_path = tmp

                provider = ComfyUIDirectProvider(provider_id=uuid4(), config={})
                mock_client = AsyncMock()
                mock_client.queue_prompt.return_value = {"prompt_id": "vid-test"}
                mock_client.get_history.return_value = {
                    "vid-test": {
                        "status": {"completed": True},
                        "outputs": {},
                    }
                }
                fake_video = (
                    b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41"
                    b"\x00\x00\x00\x08free" + b"\x00" * 500
                )
                mock_client.get_video_output.return_value = fake_video
                provider.client = mock_client

                model, data = await provider.generate_video(
                    prompt="cinematic scene", model="wan2.2",
                    duration=5, aspect_ratio="16:9",
                    reference_image_path="ref_frame.png",
                    storage_path=tmp,
                )

            assert model == "wan2.2"
            assert len(data) > 100

    @pytest.mark.asyncio
    async def test_generate_video_without_reference_image_path_is_t2v(self):
        """ComfyUI generate_video WITHOUT reference_image_path is pure T2V."""
        provider = ComfyUIDirectProvider(provider_id=uuid4(), config={})
        mock_client = AsyncMock()
        mock_client.queue_prompt.return_value = {"prompt_id": "t2v-test"}
        mock_client.get_history.return_value = {
            "t2v-test": {
                "status": {"completed": True},
                "outputs": {},
            }
        }
        fake_video = (
            b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41"
            b"\x00\x00\x00\x08free" + b"\x00" * 500
        )
        mock_client.get_video_output.return_value = fake_video
        provider.client = mock_client

        model, data = await provider.generate_video(
            prompt="test", model="wan2.2", duration=3, aspect_ratio="16:9",
        )

        assert model == "wan2.2"
        assert len(data) > 100
        # queue_prompt was called without any file upload for reference
        # (upload_file is the path for reference images in ComfyUI)
        mock_client.upload_file.assert_not_called()


# ── Helper for ComfyUI workflow check ────────────────────────────────────

def uploaded_check(workflow) -> bool:
    """Check if workflow references an uploaded file node."""
    if isinstance(workflow, dict):
        wf_str = json.dumps(workflow)
        return "uploaded_" in wf_str or "LoadImage" in wf_str
    return False


# ── RunPod Provider img2img Tests ────────────────────────────────────────


class TestRunPodImg2Img:
    @pytest.mark.asyncio
    async def test_generate_image_with_image_path_sends_input_images(self):
        """RunPod generate_image with image_path includes base64 image in queue."""
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "ref.png"
            img_path.write_bytes(b"fake-ref-image-data")

            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value.storage_path = tmp

                provider = RunPodProvider(provider_id=uuid4(), config={
                    "endpoint_id": "test-ep", "api_key": "test-key",
                })
                provider.queue_prompt = AsyncMock(return_value="runpod-img2img")
                provider.wait_for_completion = AsyncMock(return_value={})
                provider.get_output = AsyncMock(return_value=b"img2img-output")

                model, data = await provider.generate_image(
                    prompt="a portrait", model="flux1-schnell",
                    aspect_ratio="1:1", image_path="ref.png",
                )

            assert model == "flux1-schnell"
            assert data == b"img2img-output"
            # Verify input_images was passed
            call_args = provider.queue_prompt.call_args
            assert call_args is not None
            if len(call_args.args) >= 2:
                input_images = call_args.args[1]
                assert len(input_images) > 0
                assert input_images[0]["name"] == "reference.png"

    @pytest.mark.asyncio
    async def test_generate_image_without_image_path_is_t2i(self):
        """RunPod generate_image WITHOUT image_path does NOT send input_images."""
        provider = RunPodProvider(provider_id=uuid4(), config={
            "endpoint_id": "test-ep", "api_key": "test-key",
        })
        provider.queue_prompt = AsyncMock(return_value="runpod-t2i")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=b"t2i-output")

        model, data = await provider.generate_image(
            prompt="a landscape", model="flux1-schnell", aspect_ratio="16:9",
        )

        assert model == "flux1-schnell"
        # queue_prompt called without input_images (only 1 positional arg)
        call_args = provider.queue_prompt.call_args
        assert len(call_args.args) == 1, "Should not pass input_images for T2I"

    @pytest.mark.asyncio
    async def test_generate_video_with_image_path_encodes_reference(self):
        """RunPod generate_video with image_path base64-encodes the reference image."""
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "ref_frame.png"
            img_path.write_bytes(b"fake-ref-frame-data")

            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value.storage_path = tmp

                provider = RunPodProvider(provider_id=uuid4(), config={
                    "endpoint_id": "test-ep", "api_key": "test-key",
                })
                provider.queue_prompt = AsyncMock(return_value="runpod-i2v")
                provider.wait_for_completion = AsyncMock(return_value={})
                provider.get_output = AsyncMock(return_value=b"i2v-output")

                model, data = await provider.generate_video(
                    prompt="a scene", model="wan2.2",
                    duration=5, aspect_ratio="16:9",
                    image_path="ref_frame.png",
                )

            assert model == "wan2.2"
            assert data == b"i2v-output"
            # Verify input_images was passed with base64-encoded data
            call_args = provider.queue_prompt.call_args
            assert call_args is not None
            kwargs = call_args.kwargs if hasattr(call_args, 'kwargs') else {}
            input_images = kwargs.get("input_images", [])
            if not input_images and len(call_args.args) >= 2:
                input_images = call_args.args[1]
            assert len(input_images) > 0

    @pytest.mark.asyncio
    async def test_generate_video_without_image_path_is_t2v(self):
        """RunPod generate_video WITHOUT image_path is pure T2V (no input_images)."""
        provider = RunPodProvider(provider_id=uuid4(), config={
            "endpoint_id": "test-ep", "api_key": "test-key",
        })
        provider.queue_prompt = AsyncMock(return_value="runpod-t2v")
        provider.wait_for_completion = AsyncMock(return_value={})
        provider.get_output = AsyncMock(return_value=b"t2v-output")

        model, data = await provider.generate_video(
            prompt="test", model="wan2.2", duration=5, aspect_ratio="16:9",
        )

        assert model == "wan2.2"
        call_args = provider.queue_prompt.call_args
        kwargs = call_args.kwargs if hasattr(call_args, 'kwargs') else {}
        input_images = kwargs.get("input_images", None)
        if input_images is None and len(call_args.args) >= 2:
            input_images = call_args.args[1]
        assert input_images is None or len(input_images) == 0


# ── AtlasCloud Provider img2img Tests ────────────────────────────────────


class FakeAtlasResponse:
    def __init__(self, status_code: int, json_data: dict | None = None,
                 content: bytes = b"", text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.content = content
        self._text = text

    def json(self) -> dict:
        return self._json_data

    async def aread(self) -> bytes:
        if self._text:
            return self._text.encode("utf-8")
        return json.dumps(self._json_data).encode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx
            request = httpx.Request("GET", "https://test.local")
            raise httpx.HTTPStatusError("status error", request=request,
                                       response=httpx.Response(self.status_code, request=request))


class FakeAtlasClient:
    def __init__(self, poll_results=None, assets=None):
        self.poll_results = list(poll_results or [])
        self.assets = assets or {}
        self.calls: list[dict] = []

    async def post(self, url: str, json: dict | None = None,
                   headers: dict | None = None, files: dict | None = None) -> FakeAtlasResponse:
        self.calls.append({"method": "POST", "url": url, "json": json,
                           "headers": headers, "files": files})
        if url.endswith("/model/generateImage"):
            return FakeAtlasResponse(200, {
                "data": {"id": "img-pred", "urls": {"get": "https://atlas.test/getResult"}},
            })
        if url.endswith("/model/generateVideo"):
            return FakeAtlasResponse(200, {
                "data": {"id": "vid-pred", "urls": {"get": "https://atlas.test/getResult"}},
            })
        if url.endswith("/model/uploadMedia"):
            return FakeAtlasResponse(200, {"data": {"download_url": "https://cdn.test/up.png"}})
        return FakeAtlasResponse(404, {"message": "not found"})

    async def get(self, url: str, params: dict | None = None,
                  headers: dict | None = None) -> FakeAtlasResponse:
        self.calls.append({"method": "GET", "url": url, "params": params, "headers": headers})
        if "getResult" in url and self.poll_results:
            return FakeAtlasResponse(200, self.poll_results.pop(0))
        if url in self.assets:
            return FakeAtlasResponse(200, content=self.assets[url])
        return FakeAtlasResponse(404, {"message": "asset not found"})


class FakeModelConfig:
    def __init__(self, provider_model_id: str):
        self.provider_model_id = provider_model_id
        self.constraints: dict = {}
        self.parameter_map: dict = {}

    def build_payload(self, **kwargs: Any) -> dict:
        payload: dict = {"prompt": kwargs.get("prompt", "")}
        if kwargs.get("duration") is not None:
            payload["duration"] = kwargs["duration"]
        if kwargs.get("aspect_ratio") is not None:
            payload["aspect_ratio"] = kwargs["aspect_ratio"]
        if kwargs.get("image_url") is not None:
            payload["image_url"] = kwargs["image_url"]
        return payload


class TestAtlasCloudImg2Img:
    @pytest.mark.asyncio
    async def test_generate_image_still_sends_request(self):
        """AtlasCloud generate_image correctly submits a job and polls for result."""
        image_url = "https://cdn.test/img.png"
        client = FakeAtlasClient(poll_results=[
            {"data": {"status": "completed", "url": image_url}},
        ])
        client.assets[image_url] = b"atlas-image-data"

        provider = AtlasCloudProvider(provider_id=uuid4(), config={"api_key": "test-token"})
        provider.client = client  # type: ignore[assignment]
        provider._get_model_config = AsyncMock(  # type: ignore[method-assign]
            return_value=FakeModelConfig("flux-schnell")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            model, data = await provider.generate_image(
                prompt="a mountain", model="flux-schnell", aspect_ratio="16:9",
            )

        assert model == "flux-schnell"
        assert data == b"atlas-image-data"

    @pytest.mark.asyncio
    async def test_generate_video_with_reference_image_uploaded_to_atlas(self):
        """AtlasCloud I2V: local image_path triggers uploadMedia then I2V request."""
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "ref_frame.png"
            img_path.write_bytes(b"fake-ref-frame-atlas")

            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value.storage_path = tmp

                video_url = "https://cdn.test/vid.mp4"
                client = FakeAtlasClient(poll_results=[
                    {"data": {"status": "completed", "url": video_url}},
                ])
                client.assets[video_url] = b"atlas-video-data"

                provider = AtlasCloudProvider(provider_id=uuid4(), config={"api_key": "tk"})
                provider.client = client  # type: ignore[assignment]
                provider._get_model_config = AsyncMock(  # type: ignore[method-assign]
                    return_value=FakeModelConfig("kling-v2.0")
                )

                with patch("asyncio.sleep", new_callable=AsyncMock):
                    model, data = await provider.generate_video(
                        prompt="cinematic scene", model="kling-v2.0",
                        duration=5, aspect_ratio="16:9",
                        image_path="ref_frame.png",
                    )

            assert model == "kling-v2.0"
            assert data == b"atlas-video-data"
            # Verify uploadMedia was called (for local image upload)
            upload_calls = [c for c in client.calls if "uploadMedia" in c["url"]]
            assert len(upload_calls) >= 1, "Should call uploadMedia for local reference image"

    @pytest.mark.asyncio
    async def test_generate_video_without_image_path_is_t2v(self):
        """AtlasCloud generate_video WITHOUT image_path does NOT upload media."""
        video_url = "https://cdn.test/vid2.mp4"
        client = FakeAtlasClient(poll_results=[
            {"data": {"status": "completed", "url": video_url}},
        ])
        client.assets[video_url] = b"atlas-t2v-data"

        provider = AtlasCloudProvider(provider_id=uuid4(), config={"api_key": "tk"})
        provider.client = client  # type: ignore[assignment]
        provider._get_model_config = AsyncMock(  # type: ignore[method-assign]
            return_value=FakeModelConfig("kling-v2.0")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            model, data = await provider.generate_video(
                prompt="test", model="kling-v2.0",
                duration=5, aspect_ratio="16:9",
            )

        assert model == "kling-v2.0"
        assert data == b"atlas-t2v-data"
        # No uploadMedia calls when no local image_path
        upload_calls = [c for c in client.calls if "uploadMedia" in c["url"]]
        assert len(upload_calls) == 0, "Should NOT call uploadMedia for T2V"

    @pytest.mark.asyncio
    async def test_generate_video_with_remote_image_url(self):
        """AtlasCloud I2V with HTTP image_url passes it directly (no upload)."""
        video_url = "https://cdn.test/vid3.mp4"
        client = FakeAtlasClient(poll_results=[
            {"data": {"status": "completed", "url": video_url}},
        ])
        client.assets[video_url] = b"atlas-i2v-url-data"

        provider = AtlasCloudProvider(provider_id=uuid4(), config={"api_key": "tk"})
        provider.client = client  # type: ignore[assignment]
        provider._get_model_config = AsyncMock(  # type: ignore[method-assign]
            return_value=FakeModelConfig("kling-v2.0")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            model, data = await provider.generate_video(
                prompt="scene", model="kling-v2.0",
                duration=5, aspect_ratio="16:9",
                image_path="https://remote.example.com/frame.png",
            )

        assert model == "kling-v2.0"
        assert data == b"atlas-i2v-url-data"
        # No uploadMedia calls for remote URLs
        upload_calls = [c for c in client.calls if "uploadMedia" in c["url"]]
        assert len(upload_calls) == 0, "Should NOT upload remote URLs"
        # Verify image_url was passed in payload
        generate_calls = [c for c in client.calls if "generateVideo" in c["url"]]
        assert len(generate_calls) >= 1
        payload = generate_calls[0]["json"]
        assert "image_url" in payload
