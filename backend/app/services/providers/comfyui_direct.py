import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.services import ComfyUIClient
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
from app.services.providers.comfyui.workflow_builders import (
    build_wan_i2v_workflow,
    build_wan_video_workflow,
)

logger = logging.getLogger(__name__)


def _duration_to_frames(duration: int, fps: int = 16) -> int:
    frames = int(duration * fps)
    if frames < 9:
        frames = 9
    if frames % 2 == 0:
        frames += 1
    return frames


class ComfyUIDirectProvider(ImageProvider, VideoProvider, ComfyUIProvider):
    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.client: ComfyUIClient | None = None
        self._max_concurrent = config.get("max_concurrent_jobs", 1)
        self._current_jobs = 0

    async def initialize(self, config: dict) -> None:
        if not config.get("comfyui_url"):
            raise ValueError("comfyui_url is required for comfyui_direct provider")
        self.client = ComfyUIClient(base_url=config["comfyui_url"])

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        result = await self.client.queue_prompt(workflow)
        return result["prompt_id"]

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 172800.0,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        elapsed = 0.0
        while elapsed < timeout:
            history = await self.client.get_history(job_id)

            if job_id in history:
                entry = history[job_id]
                status = entry.get("status", {})

                if status.get("completed", False):
                    return entry

                if progress_callback:
                    progress = 50
                    if status.get("executing"):
                        progress = 75
                    await progress_callback(progress, "Processing on local GPU...")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Local job {job_id} did not complete within {timeout}s")

    async def get_output(self, result: dict) -> bytes | None:
        if not self.client:
            raise RuntimeError("Provider not initialized")
        return await self.client.get_video_output(result)

    async def cancel_job(self, job_id: str) -> bool:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        try:
            response = await self.client.client.post(f"{self.client.base_url}/interrupt")
            return response.status_code == 200
        except Exception:
            return False

    async def get_status(self) -> ProviderInfo:
        if not self.client:
            return ProviderInfo(
                name="comfyui_direct",
                provider_type="comfyui_direct",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=0.0,
                message="Provider not initialized",
            )

        try:
            await self.client.get_system_info()
            return ProviderInfo(
                name="comfyui_direct",
                provider_type="comfyui_direct",
                is_available=True,
                estimated_wait_seconds=0,
                cost_per_job=0.0,
                message="Ready",
            )
        except Exception as e:
            return ProviderInfo(
                name="comfyui_direct",
                provider_type="comfyui_direct",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=0.0,
                message=f"Error: {str(e)}",
            )

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 60.0

    async def shutdown(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_image=True,
            supports_video=True,
            supports_llm=False,
            supports_model_sync=True,
        )

    _ERROR_PATTERNS: list[tuple[tuple[str, ...], type[ProviderError]]] = [
        (("overloaded", "capacity", "queue is full"), ProviderOverloadedError),
        (("rate limit", "429"), ProviderError),
        (("connection", "connectionerror", "connect timeout"), ProviderConnectionError),
        (("timeout", "timed out", "did not complete"), ProviderTimeoutError),
        (("comfyui error", "prompt failed"), ProviderError),
        (("no output data", "returned no output"), ProviderError),
    ]

    async def generate_image(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        reference_image_path: str | None = kwargs.get("image_path")

        if reference_image_path:
            from app.config import get_settings
            settings = get_settings()
            image_full_path = Path(settings.storage_path) / reference_image_path
            if not image_full_path.exists():
                raise FileNotFoundError(
                    f"Reference image not found: {image_full_path}"
                )

            image_name = await self.client.upload_file(
                image_full_path.name, image_full_path.read_bytes()
            )
            ip_adapter_strength = float(
                kwargs.get("reference_image_strength", 0.75)
            )

            from app.services.providers.comfyui.workflow_builders import (
                build_ip_adapter_image_workflow,
            )
            workflow = build_ip_adapter_image_workflow(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_name=image_name,
                ip_adapter_strength=ip_adapter_strength,
                provider_config=self.config,
            )
        else:
            from app.services.media_generator import (
                _build_comfyui_image_workflow,
                _build_flux_image_workflow,
            )

            if model == "flux1-schnell":
                workflow = _build_flux_image_workflow(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    provider_config=self.config,
                )
            else:
                workflow = _build_comfyui_image_workflow(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    model_preference=model,
                    provider_config=self.config,
                )

        prompt_id = await self.queue_prompt(workflow)
        result = await self.wait_for_completion(prompt_id)
        image_data = await self.get_output(result)
        if not image_data:
            raise ValueError("ComfyUI image generation returned no output data")

        return model, image_data

    async def generate_video(
        self,
        prompt: str,
        model: str,
        duration: int,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        frames = _duration_to_frames(duration)
        reference_image_path: str | None = kwargs.get("reference_image_path")

        if model.startswith("wan"):
            if reference_image_path:
                image_path = Path(kwargs.get("storage_path", ".")) / reference_image_path
                if image_path.exists():
                    image_name = await self.client.upload_file(
                        image_path.name, image_path.read_bytes()
                    )
                    workflow = build_wan_i2v_workflow(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        frames=frames,
                        image_name=image_name,
                        provider_config=self.config,
                    )
                else:
                    workflow = build_wan_video_workflow(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        frames=frames,
                        provider_config=self.config,
                    )
            else:
                workflow = build_wan_video_workflow(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    frames=frames,
                    provider_config=self.config,
                )
        else:
            raise ValueError(f"Unsupported model variant for ComfyUI direct: {model}")

        prompt_id = await self.queue_prompt(workflow)
        result = await self.wait_for_completion(prompt_id)
        output_data = await self.get_output(result)
        if not output_data:
            raise ValueError("ComfyUI video generation returned no output data")

        return model, output_data

    async def sync_models(self) -> list[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        models: list[dict[str, Any]] = []
        try:
            response = await self.client.client.get(
                f"{self.client.base_url}/object_info/UNETLoader"
            )
            response.raise_for_status()
            info = response.json()
            unet_values = (
                info.get("UNETLoader", {})
                .get("input", {})
                .get("required", {})
                .get("unet_name", [[]])[0]
            )
            for name in unet_values:
                model_type = "video" if "wan" in name.lower() else "image"
                models.append({
                    "model_id": f"comfyui_unet:{name}",
                    "name": name,
                    "type": model_type,
                    "category": "unet",
                })
        except Exception as e:
            logger.warning("Failed to sync UNET models from ComfyUI: %s", e)

        try:
            response = await self.client.client.get(
                f"{self.client.base_url}/object_info/CLIPLoader"
            )
            response.raise_for_status()
            info = response.json()
            clip_values = (
                info.get("CLIPLoader", {})
                .get("input", {})
                .get("required", {})
                .get("clip_name", [[]])[0]
            )
            for name in clip_values:
                models.append({
                    "model_id": f"comfyui_clip:{name}",
                    "name": name,
                    "type": "clip",
                    "category": "clip",
                })
        except Exception as e:
            logger.warning("Failed to sync CLIP models from ComfyUI: %s", e)

        try:
            response = await self.client.client.get(
                f"{self.client.base_url}/object_info/VAELoader"
            )
            response.raise_for_status()
            info = response.json()
            vae_values = (
                info.get("VAELoader", {})
                .get("input", {})
                .get("required", {})
                .get("vae_name", [[]])[0]
            )
            for name in vae_values:
                models.append({
                    "model_id": f"comfyui_vae:{name}",
                    "name": name,
                    "type": "vae",
                    "category": "vae",
                })
        except Exception as e:
            logger.warning("Failed to sync VAE models from ComfyUI: %s", e)

        return models

    async def list_models(self) -> list[dict[str, Any]]:
        return await self.sync_models()
