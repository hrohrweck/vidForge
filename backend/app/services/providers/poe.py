import asyncio
import base64
import json
from typing import Any, Awaitable, Callable
from uuid import UUID

import httpx

from app.services.providers.base import ComfyUIProvider, JobResult, ProviderInfo


class PoeProvider(ComfyUIProvider):
    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.api_key = config.get("api_key", "")
        self.base_url = "https://api.poe.com/v1"
        self.client: httpx.AsyncClient | None = None
        self._max_concurrent = config.get("max_concurrent_jobs", 1)
        self._current_jobs = 0
        self._available_models: list[dict] = []
        self._model_cache: dict[str, dict] = {}

    async def initialize(self, config: dict) -> None:
        if not config.get("api_key"):
            raise ValueError("api_key is required for Poe provider")
        self.api_key = config["api_key"]
        self.client = httpx.AsyncClient(timeout=300.0)
        await self._discover_models()

    async def _discover_models(self) -> None:
        if not self.client:
            return

        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                self._available_models = data.get("data", [])
                self._model_cache = {
                    m["id"]: m for m in self._available_models
                }
        except Exception:
            pass

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        raise NotImplementedError("Poe provider uses different method for media generation")

    # Aspect ratio to size mapping for Poe Videos API
    _ASPECT_RATIO_SIZES: dict[str, str] = {
        "16:9": "1920x1080",
        "9:16": "1080x1920",
        "1:1": "1080x1080",
        "4:3": "1440x1080",
        "3:4": "1080x1440",
        "3:2": "1440x960",
        "2:3": "960x1440",
    }

    async def generate_video(
        self,
        prompt: str,
        model: str = "Veo-3",
        duration: int = 10,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        negative_prompt: str = "",
        image_path: str | None = None,
    ) -> tuple[str, bytes | None]:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        import logging
        logger = logging.getLogger(__name__)

        # Use Poe Videos API (/v1/videos) for video generation
        size = self._ASPECT_RATIO_SIZES.get(aspect_ratio, "1920x1080")

        create_body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "seconds": min(duration, 8),  # Veo models max 8s
            "size": size,
        }

        # Add reference image as base64 input_image if available
        if image_path:
            from pathlib import Path
            from app.config import get_settings
            settings = get_settings()
            full_image_path = Path(settings.storage_path) / image_path
            if full_image_path.exists():
                image_bytes = full_image_path.read_bytes()
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                create_body["input_image"] = f"data:image/png;base64,{image_b64}"

        logger.info(f"Poe generate_video: model={model}, size={size}, seconds={create_body['seconds']}, has_image={'input_image' in create_body}")

        # Step 1: Create video
        create_response = await self.client.post(
            f"{self.base_url}/videos",
            json=create_body,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

        if create_response.status_code not in (200, 201):
            error_msg = create_response.text
            raise RuntimeError(f"Poe Videos API create error: {error_msg}")

        video_data = create_response.json()
        video_id = video_data.get("id", "")
        status = video_data.get("status", "queued")

        logger.info(f"Poe video created: id={video_id}, status={status}")

        # Step 2: Poll until completed
        poll_interval = 5.0
        timeout = 300.0
        elapsed = 0.0

        while status in ("queued", "in_progress") and elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_response = await self.client.get(
                f"{self.base_url}/videos/{video_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

            if poll_response.status_code != 200:
                raise RuntimeError(f"Poe Videos API poll error: {poll_response.text}")

            video_data = poll_response.json()
            status = video_data.get("status", "failed")
            progress = video_data.get("progress", 0)
            logger.info(f"Poe video poll: id={video_id}, status={status}, progress={progress}")

        if status == "failed":
            error = video_data.get("error", {})
            raise RuntimeError(f"Poe video generation failed: {error}")

        if status != "completed":
            raise RuntimeError(f"Poe video generation timed out after {timeout}s (status={status})")

        # Step 3: Download video content
        download_response = await self.client.get(
            f"{self.base_url}/videos/{video_id}/content",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

        if download_response.status_code != 200:
            raise RuntimeError(f"Poe Videos API download error: {download_response.text}")

        video_bytes = download_response.content
        logger.info(f"Poe video downloaded: id={video_id}, size={len(video_bytes)} bytes")

        return video_id, video_bytes

    async def generate_image(
        self,
        prompt: str,
        model: str = "GPT-Image-1",
        aspect_ratio: str = "3:2",
        quality: str = "high",
        negative_prompt: str = "",
        image_path: str | None = None,
    ) -> tuple[str, bytes | None]:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        # Build message content with optional image (OpenAI vision format)
        content: list[dict[str, Any]] | str
        if image_path:
            from pathlib import Path
            from app.config import get_settings
            settings = get_settings()
            full_image_path = Path(settings.storage_path) / image_path
            if full_image_path.exists():
                image_bytes = full_image_path.read_bytes()
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        },
                    },
                    {"type": "text", "text": prompt},
                ]
            else:
                content = prompt
        else:
            content = prompt
        messages = [{"role": "user", "content": content}]
        if negative_prompt:
            messages.append({"role": "user", "content": f"Negative: {negative_prompt}"})

        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Poe generate_image request: model={model}, has_image={image_path is not None}")

        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

        if response.status_code != 200:
            error_msg = response.text
            raise RuntimeError(f"Poe API error: {error_msg}")

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        return result.get("id", ""), self._parse_media_content(content)

    def _parse_media_content(self, content: str) -> bytes | None:
        if not content:
            return None

        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if "image_base64" in data:
                    return base64.b64decode(data["image_base64"])
                elif "video_base64" in data:
                    return base64.b64decode(data["video_base64"])
                elif "image_url" in data:
                    return None
                elif "video_url" in data:
                    return None
        except (json.JSONDecodeError, ValueError):
            pass

        if "data:image" in content or "data:video" in content:
            return None

        return None

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict:
        return {"status": "completed", "job_id": job_id}

    async def get_output(self, result: dict) -> bytes | None:
        return result.get("output_data")

    async def cancel_job(self, job_id: str) -> bool:
        return False

    async def get_status(self) -> ProviderInfo:
        if not self.client:
            return ProviderInfo(
                name="poe",
                provider_type="poe",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=None,
                message="Provider not initialized",
            )

        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if response.status_code == 200:
                video_models = self.get_models_by_modality("video")
                image_models = self.get_models_by_modality("image")
                return ProviderInfo(
                    name="poe",
                    provider_type="poe",
                    is_available=True,
                    estimated_wait_seconds=60,
                    cost_per_job=0.0,
                    message=f"Ready - {len(video_models)} video, {len(image_models)} image models available",
                )
        except Exception as e:
            return ProviderInfo(
                name="poe",
                provider_type="poe",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=None,
                message=f"Error: {str(e)}",
            )

        return ProviderInfo(
            name="poe",
            provider_type="poe",
            is_available=False,
            estimated_wait_seconds=0,
            cost_per_job=None,
            message="API key invalid or Poe service unavailable",
        )

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 60.0

    async def shutdown(self) -> None:
        if self.client:
            await self.client.aclose()

    def get_models_by_modality(self, modality: str) -> list[dict]:
        return [
            m
            for m in self._available_models
            if m.get("architecture", {}).get("output_modalities", []).count(modality) > 0
        ]

    def get_video_models(self) -> list[dict]:
        return self.get_models_by_modality("video")

    def get_image_models(self) -> list[dict]:
        return self.get_models_by_modality("image")

    def get_text_models(self) -> list[dict]:
        text_only = [
            m
            for m in self._available_models
            if m.get("architecture", {}).get("output_modalities") == ["text"]
        ]
        return text_only


async def create_poe_provider(provider_id: UUID, config: dict) -> PoeProvider:
    provider = PoeProvider(provider_id, config)
    await provider.initialize(config)
    return provider
