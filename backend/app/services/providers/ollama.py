import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.services.providers.base import ComfyUIProvider, ProviderInfo

logger = logging.getLogger(__name__)


class OllamaProvider(ComfyUIProvider):
    """Text-only provider for local Ollama LLM models.

    Does NOT support image/video generation — only text completion/chat.
    Used exclusively via LLMService for prompt planning, script generation, etc.
    """

    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.base_url = config.get("base_url", "http://ollama:11434")

    async def initialize(self, config: dict) -> None:
        pass

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(
            name="Ollama",
            provider_type="ollama",
            is_available=True,
            cost_per_job=0.0,
        )

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 1.0

    async def shutdown(self) -> None:
        pass

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        raise NotImplementedError("Ollama is text-only")

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 172800.0,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict:
        raise NotImplementedError("Ollama is text-only")

    async def get_output(self, result: dict) -> bytes | None:
        raise NotImplementedError("Ollama is text-only")

    async def cancel_job(self, job_id: str) -> bool:
        raise NotImplementedError("Ollama is text-only")
