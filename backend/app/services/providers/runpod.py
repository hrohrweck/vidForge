import asyncio
import base64
import logging
import random
from decimal import Decimal
from typing import Any, Awaitable, Callable
from uuid import UUID

import httpx

from app.services.providers.base import (
    ComfyUIProvider,
    ImageProvider,
    ProviderCapabilities,
    ProviderConnectionError,
    ProviderError,
    ProviderInfo,
    ProviderOverloadedError,
    ProviderTimeoutError,
    VideoProvider,
)
from app.services.providers.comfyui.workflow_builders import build_wan_video_workflow

logger = logging.getLogger(__name__)


class RunPodProvider(ComfyUIProvider, ImageProvider, VideoProvider):
    """RunPod serverless endpoint provider for ComfyUI workflows.

    Implements both ImageProvider and VideoProvider interfaces for
    the new provider abstraction layer, while maintaining backward
    compatibility with the legacy ComfyUIProvider contract.
    """

    BASE_URL = "https://api.runpod.ai/v2"

    # RunPod-specific error patterns, checked before the default ProviderBase patterns.
    _ERROR_PATTERNS: list[tuple[tuple[str, ...], type[ProviderError]]] = [
        (("cold start", "instance starting", "warming up"), ProviderTimeoutError),
        (("runpod job failed", "runpod error"), ProviderError),
        (("runpod job was cancelled", "cancelled"), ProviderError),
        (("runpod api error", "runpod status check failed"), ProviderConnectionError),
        (("runpod returned no output", "no output data"), ProviderError),
        (("endpoint not found", "invalid endpoint"), ProviderConnectionError),
        # Inherit default patterns from ProviderBase
        (("overloaded", "capacity", "queue is full"), ProviderOverloadedError),
        (("rate limit", "429"), ProviderError),
        (("connection", "connectionerror"), ProviderConnectionError),
        (("timeout", "timed out"), ProviderTimeoutError),
    ]

    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.client: httpx.AsyncClient | None = None
        self.endpoint_id = config.get("endpoint_id", "")
        self.api_key = config.get("api_key", "")
        self.cost_per_gpu_hour = Decimal(str(config.get("cost_per_gpu_hour", 0.69)))
        self.idle_timeout = config.get("idle_timeout_seconds", 30)
        self.flashboot_enabled = config.get("flashboot_enabled", True)
        self.max_workers = config.get("max_workers", 3)

    async def initialize(self, config: dict) -> None:
        self.endpoint_id = config.get("endpoint_id", self.endpoint_id)
        self.api_key = config.get("api_key", self.api_key)
        self.cost_per_gpu_hour = Decimal(
            str(config.get("cost_per_gpu_hour", str(self.cost_per_gpu_hour)))
        )

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=30.0),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    def _get_endpoint_url(self, path: str = "") -> str:
        return f"{self.BASE_URL}/{self.endpoint_id}{path}"

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        if not self.client:
            raise RuntimeError("RunPod provider not initialized")

        response = await self.client.post(
            self._get_endpoint_url("/run"), json={"input": {"workflow": workflow}}
        )

        if response.status_code >= 400:
            error_detail = response.text
            raise Exception(f"RunPod API error {response.status_code}: {error_detail}")

        data = response.json()
        return data["id"]

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 172800.0,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict:
        if not self.client:
            raise RuntimeError("RunPod provider not initialized")

        elapsed = 0.0
        cold_start_reported = False
        last_status = None

        while elapsed < timeout:
            try:
                response = await self.client.get(self._get_endpoint_url(f"/status/{job_id}"))

                if response.status_code >= 400:
                    raise Exception(f"RunPod status check failed: {response.status_code}")

                data = response.json()
                status = data.get("status", "UNKNOWN")

                if status != last_status and progress_callback:
                    last_status = status

                    if status == "IN_QUEUE":
                        if not cold_start_reported:
                            await progress_callback(
                                0, "Starting RunPod instance (cold start ~30-60s)..."
                            )
                            cold_start_reported = True
                        else:
                            await progress_callback(5, "Job queued on RunPod...")
                    elif status == "IN_PROGRESS":
                        await progress_callback(25, "Processing on RunPod GPU...")

                if status == "COMPLETED":
                    return data.get("output", {})

                if status == "FAILED":
                    error = data.get("error", "Unknown RunPod error")
                    raise Exception(f"RunPod job failed: {error}")

                if status == "CANCELLED":
                    raise Exception("RunPod job was cancelled")

            except httpx.HTTPError as e:
                if progress_callback:
                    await progress_callback(0, f"Connection error, retrying... ({str(e)})")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"RunPod job {job_id} timed out after {timeout}s")

    async def get_output(self, result: dict) -> bytes | None:
        if "images" in result:
            for img in result["images"]:
                if "image" in img:
                    return base64.b64decode(img["image"])

        if "videos" in result:
            for vid in result["videos"]:
                if "video" in vid:
                    return base64.b64decode(vid["video"])

        if "output" in result:
            output = result["output"]
            if "images" in output:
                for img in output["images"]:
                    if "image" in img:
                        return base64.b64decode(img["image"])
            if "videos" in output:
                for vid in output["videos"]:
                    if "video" in vid:
                        return base64.b64decode(vid["video"])

        return None

    async def cancel_job(self, job_id: str) -> bool:
        if not self.client:
            return False

        try:
            response = await self.client.post(self._get_endpoint_url(f"/cancel/{job_id}"))
            return response.status_code == 200
        except Exception:
            return False

    async def get_status(self) -> ProviderInfo:
        if not self.client:
            return ProviderInfo(
                name="runpod",
                provider_type="runpod",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=None,
                message="Provider not initialized",
            )

        try:
            response = await self.client.get(self._get_endpoint_url("/health"))
            data = response.json()

            status = data.get("status", "UNKNOWN")
            is_available = status in ("RUNNING", "READY")

            workers_ready = data.get("workers", {}).get("ready", 0)
            estimated_wait = 0 if workers_ready > 0 else 45

            return ProviderInfo(
                name="runpod",
                provider_type="runpod",
                is_available=is_available,
                estimated_wait_seconds=estimated_wait,
                cost_per_job=None,
                message=f"Ready ({workers_ready} workers)"
                if workers_ready > 0
                else "Cold start required",
            )
        except Exception as e:
            return ProviderInfo(
                name="runpod",
                provider_type="runpod",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=None,
                message=f"Error: {str(e)}",
            )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_image=True,
            supports_video=True,
            supports_llm=False,
            supports_model_sync=True,
        )

    async def generate_image(
        self,
        prompt: str,
        model: str = "flux1-schnell",
        aspect_ratio: str = "16:9",
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        workflow = self._build_image_workflow(prompt, aspect_ratio)
        progress_callback = kwargs.get("progress_callback")
        run_id = await self.queue_prompt(workflow)
        result = await self.wait_for_completion(run_id, progress_callback=progress_callback)
        output_data = await self.get_output(result)
        if not output_data:
            raise RuntimeError("RunPod returned no image data")
        return (model, output_data)

    async def generate_video(
        self,
        prompt: str,
        model: str = "wan2.2",
        duration: int = 5,
        aspect_ratio: str = "16:9",
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        fps = int(self.config.get("wan_video_fps") or 16)
        frames = max(duration * fps, 9)
        if frames % 2 == 0:
            frames += 1
        workflow = build_wan_video_workflow(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            frames=frames,
            provider_config=self.config,
        )
        progress_callback = kwargs.get("progress_callback")
        run_id = await self.queue_prompt(workflow)
        result = await self.wait_for_completion(run_id, progress_callback=progress_callback)
        output_data = await self.get_output(result)
        if not output_data:
            raise RuntimeError("RunPod returned no video data")
        return (model, output_data)

    async def sync_models(self) -> list[dict[str, Any]]:
        info = await self.get_endpoint_info()
        models = self._default_models()
        if info:
            for m in models:
                m["endpoint_available"] = info.get("status") in ("RUNNING", "READY")
        return models

    async def list_models(self) -> list[dict[str, Any]]:
        return self._default_models()

    def _default_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "wan2.2",
                "name": "Wan 2.2",
                "type": "video",
                "capabilities": ["text-to-video", "image-to-video"],
                "provider_type": "runpod",
            },
            {
                "id": "flux1-schnell",
                "name": "Flux.1 Schnell",
                "type": "image",
                "capabilities": ["text-to-image"],
                "provider_type": "runpod",
            },
        ]

    @staticmethod
    def _image_resolution(aspect_ratio: str) -> tuple[int, int]:
        ratios = {
            "16:9": (1280, 720),
            "9:16": (720, 1280),
            "1:1": (1024, 1024),
            "4:3": (1024, 768),
            "3:2": (1152, 768),
            "21:9": (1680, 720),
        }
        return ratios.get(aspect_ratio, (1280, 720))

    def _build_image_workflow(self, prompt: str, aspect_ratio: str) -> dict[str, Any]:
        width, height = self._image_resolution(aspect_ratio)
        seed = random.randint(0, 2**31 - 1)

        unet_name = str(self.config.get("flux_unet_name") or "flux1-schnell-fp8.safetensors")
        clip_name1 = str(self.config.get("flux_clip_name1") or "clip_l.safetensors")
        clip_name2 = str(self.config.get("flux_clip_name2") or "t5xxl_fp8_e4m3fn.safetensors")
        vae_name = str(self.config.get("flux_vae_name") or "ae.safetensors")

        return {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
            },
            "2": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": clip_name1, "clip_name2": clip_name2, "type": "flux"},
            },
            "3": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": vae_name},
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["2", 0]},
            },
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "", "clip": ["2", 0]},
            },
            "6": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "7": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 4,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["4", 0],
                    "negative": ["5", 0],
                    "latent_image": ["6", 0],
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"images": ["8", 0], "filename_prefix": "vidforge"},
            },
        }

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        estimated_seconds = await self.estimate_duration(workflow)
        cost_per_second = self.cost_per_gpu_hour / 3600
        return float(cost_per_second * Decimal(str(estimated_seconds)))

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        pipeline = workflow.get("pipeline", [])
        base_duration = 30.0

        for step in pipeline:
            step_name = step.get("step", "")
            if "video" in step_name.lower() or "generate" in step_name.lower():
                base_duration += 45.0
            elif "audio" in step_name.lower():
                base_duration += 15.0
            elif "merge" in step_name.lower():
                base_duration += 10.0

        return min(base_duration, 600.0)

    async def shutdown(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    async def get_endpoint_info(self) -> dict:
        if not self.client:
            return {}

        try:
            response = await self.client.get(self._get_endpoint_url("/health"))
            return response.json()
        except Exception:
            return {}
