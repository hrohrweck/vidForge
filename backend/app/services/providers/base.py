from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services.llm_service import LLMChunk
from app.services.model_capabilities import ModelCapability


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


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_image: bool = False
    supports_video: bool = False
    supports_llm: bool = False
    supports_model_sync: bool = False
    capabilities: list[ModelCapability] = field(default_factory=list)


@dataclass(frozen=True)
class ModelListResult:
    provider_id: str
    models: list[dict[str, Any]]


@dataclass(frozen=True)
class SyncResult:
    provider_id: str
    synced_models: list[dict[str, Any]]


class ProviderError(Exception):
    """Base error for provider operations."""


class ProviderOverloadedError(ProviderError):
    """Raised when a provider is overloaded or at capacity."""


class ProviderRateLimitError(ProviderError):
    """Raised when requests are rate-limited."""


class ProviderConnectionError(ProviderError):
    """Raised when provider connectivity fails."""


class ProviderTimeoutError(ProviderError):
    """Raised when provider operations time out."""


class ProviderBase(ABC):
    # Class-level pattern catalog used by the default ``classify_error`` impl.
    # Subclasses can extend (or override) this list to add provider-specific
    # error mapping. Order matters — first matching pattern wins.
    _ERROR_PATTERNS: list[tuple[tuple[str, ...], type[ProviderError]]] = [
        (("overloaded", "capacity", "queue is full"), ProviderOverloadedError),
        (("rate limit", "429"), ProviderRateLimitError),
        (("connection", "connectionerror"), ProviderConnectionError),
        (("timeout", "timed out"), ProviderTimeoutError),
    ]

    @abstractmethod
    async def initialize(self, config: dict[str, Any]) -> None:
        """Initialize provider with configuration."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup provider resources."""
        ...

    @abstractmethod
    async def get_status(self) -> ProviderInfo:
        """Get current provider status."""
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return capability flags for this provider."""
        ...

    def classify_error(self, exc: Exception) -> ProviderError:
        """Map arbitrary exceptions to provider-specific error types.

        Default implementation matches common error patterns in the exception
        message (case-insensitive) against ``_ERROR_PATTERNS``. Subclasses can
        either extend ``_ERROR_PATTERNS`` with provider-specific patterns or
        override this method entirely for custom classification logic.
        """
        msg = str(exc).lower()
        for patterns, error_class in self._ERROR_PATTERNS:
            if any(p in msg for p in patterns):
                return error_class(str(exc))
        return ProviderError(str(exc))

    async def sync_models(self) -> list[dict[str, Any]]:
        """Synchronize provider models into local configuration."""
        raise NotImplementedError("Provider does not support model sync")

    async def list_models(self) -> list[dict[str, Any]]:
        """List models available from this provider."""
        raise NotImplementedError("Provider does not support model listing")


class ImageProvider(ProviderBase, ABC):
    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        """Generate an image and return (asset_id, image_bytes)."""
        ...


class VideoProvider(ProviderBase, ABC):
    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        model: str,
        duration: int,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        """Generate a video and return (asset_id, video_bytes)."""
        ...


class LLMProvider(ProviderBase, ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        """Primary chat interface that yields LLMChunk responses."""
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        """Stream chat responses as LLMChunk items."""
        ...

    @abstractmethod
    def supports_tools(self, model: str) -> bool:
        """Return True if the given model supports tool calling."""
        ...


class ComfyUIProvider(ABC):
    """Deprecated provider contract kept for migration compatibility."""

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
