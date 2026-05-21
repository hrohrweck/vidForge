import json

import httpx

from app.config import get_settings


class ModelManagerError(Exception):
    pass


class ModelManager:
    """Manages Ollama model availability, checking and pulling required models on startup."""

    def __init__(self) -> None:
        settings = get_settings()
        self.ollama_url = settings.ollama_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def list_available_models(self) -> list[str]:
        """List all models currently available in Ollama."""
        try:
            response = await self.client.get(f"{self.ollama_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except httpx.HTTPError as e:
            raise ModelManagerError(f"Failed to list Ollama models: {e}")

    async def is_model_available(self, model_name: str) -> bool:
        """Check if a specific model is already pulled."""
        available = await self.list_available_models()
        return model_name in available

    async def pull_model(self, model_name: str) -> None:
        """Pull a model from Ollama. Handles the streamed progress response."""
        try:
            async with self.client.stream(
                "POST",
                f"{self.ollama_url}/api/pull",
                json={"name": model_name},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    status = chunk.get("status", "")
                    if "error" in chunk:
                        error_msg = chunk["error"]
                        if "file does not exist" in error_msg.lower():
                            raise ModelManagerError(
                                f"Model '{model_name}' does not exist in the Ollama library. "
                                f"It may need to be installed manually or is not supported."
                            )
                        raise ModelManagerError(
                            f"Failed to pull {model_name}: {error_msg}"
                        )

                    if chunk.get("completed") is True or status == "success":
                        return

        except httpx.HTTPError as e:
            raise ModelManagerError(f"Failed to pull {model_name}: {e}")

    async def ensure_models(self, required_models: list[str]) -> dict[str, str]:
        """Ensure all required models are available, pulling any that are missing.

        Returns a dict mapping model name to status:
        - "available": already present
        - "pulled": successfully pulled
        - "missing": not available and could not be pulled
        """
        available = await self.list_available_models()
        results: dict[str, str] = {}

        for model in required_models:
            if model in available:
                results[model] = "available"
            else:
                try:
                    await self.pull_model(model)
                    results[model] = "pulled"
                except ModelManagerError:
                    results[model] = "missing"

        return results

    @staticmethod
    def get_required_models() -> list[str]:
        """Return the list of models required by this application."""
        settings = get_settings()
        llm_model = getattr(settings, "llm_model", None) or "qwen3.6:35b"
        return [llm_model]
