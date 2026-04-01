import asyncio
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.services import ComfyUIClient
from app.services.providers.base import ComfyUIProvider, ProviderInfo


class ComfyUIDirectProvider(ComfyUIProvider):
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
                    await progress_callback(progress, f"Processing on local GPU...")

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
            info = await self.client.get_system_info()
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
