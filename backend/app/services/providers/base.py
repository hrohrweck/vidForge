from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import UUID


@dataclass
class ProviderInfo:
    name: str
    provider_type: str
    is_available: bool
    estimated_wait_seconds: float = 0.0
    cost_per_job: float | None = None
    message: str = ""


@dataclass
class JobResult:
    success: bool
    output_data: bytes | None = None
    error_message: str | None = None
    duration_seconds: float = 0.0
    cost: float = 0.0


class ComfyUIProvider(ABC):
    @abstractmethod
    async def initialize(self, config: dict) -> None:
        """Initialize provider with configuration."""
        ...

    @abstractmethod
    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """Submit workflow, return job ID."""
        ...

    @abstractmethod
    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 172800.0,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict:
        """Wait for job completion, return result."""
        ...

    @abstractmethod
    async def get_output(self, result: dict) -> bytes | None:
        """Extract output from result."""
        ...

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel running job."""
        ...

    @abstractmethod
    async def get_status(self) -> ProviderInfo:
        """Get current provider status."""
        ...

    @abstractmethod
    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        """Estimate cost for workflow in USD."""
        ...

    @abstractmethod
    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        """Estimate duration for workflow in seconds."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup provider resources."""
        ...
