import asyncio
import base64
from decimal import Decimal
from typing import Any, Awaitable, Callable
from uuid import UUID

import httpx

from app.services.providers.base import ComfyUIProvider, ProviderInfo


class RunPodProvider(ComfyUIProvider):
    BASE_URL = "https://api.runpod.ai/v2"

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
