# Writing AI Providers

This guide explains how to add a new AI provider (e.g., Replicate,
Stability AI, Google Gemini, custom ComfyUI setup) to VidForge.

## Provider Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Provider (database row)                                  │
│  • name, provider_type, is_active, config (JSON)          │
│  • config is a dict of provider-specific settings         │
├──────────────────────────────────────────────────────────┤
│  Provider Instance (Python class)                         │
│  • Extends ProviderBase                                   │
│  • Mixes in capability interfaces:                        │
│    ImageProvider | VideoProvider | LLMProvider            │
│  • Implements initialize(), get_status(), shutdown(),     │
│    get_capabilities()                                     │
├──────────────────────────────────────────────────────────┤
│  ProviderRegistry                                         │
│  • register(provider_type, provider_class)                │
│  • create(provider_type, provider_id, config) → instance  │
│  • get(provider_type) → class                             │
│  • list_types() → [str]                                   │
│  • Registration in providers/__init__.py                  │
└──────────────────────────────────────────────────────────┘
```

## Existing Provider Types

| Type | Class | Capabilities |
|---|---|---|
| `comfyui_direct` | `ComfyUIDirectProvider` | Image + Video |
| `runpod` | `RunPodProvider` | Image + Video |
| `poe` | `PoeProvider` | Image + Video + LLM |
| `atlascloud` | `AtlasCloudProvider` | Image + Video + LLM |
| `ollama` | `OllamaProvider` | LLM only |

## Core Interfaces

### ProviderBase

All providers extend `ProviderBase` from `providers/base.py`:

```python
class ProviderBase(ABC):
    _ERROR_PATTERNS: list[tuple[tuple[str, ...], type[ProviderError]]]

    async def initialize(self, config: dict[str, Any]) -> None:
        """Initialize provider with configuration."""

    async def shutdown(self) -> None:
        """Cleanup provider resources."""

    async def get_status(self) -> ProviderInfo:
        """Get current provider status."""

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capability flags for this provider."""

    def classify_error(self, exc: Exception) -> ProviderError:
        """Map arbitrary exceptions to provider-specific error types."""

    async def sync_models(self) -> list[dict[str, Any]]:
        """Synchronize provider models into local configuration."""

    async def list_models(self) -> list[dict[str, Any]]:
        """List models available from this provider."""
```

### Capability Interfaces

A provider can implement one or more capability interfaces. Each interface
is an ABC that extends `ProviderBase`.

**ImageProvider**:

```python
class ImageProvider(ProviderBase, ABC):
    async def generate_image(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        """Generate an image. Returns (asset_id, image_bytes)."""
```

**VideoProvider**:

```python
class VideoProvider(ProviderBase, ABC):
    async def generate_video(
        self,
        prompt: str,
        model: str,
        duration: int,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        """Generate a video. Returns (asset_id, video_bytes)."""
```

**LLMProvider**:

```python
class LLMProvider(ProviderBase, ABC):
    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        """Primary chat interface that yields LLMChunk responses."""

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]:
        """Stream chat responses as LLMChunk items."""

    def supports_tools(self, model: str) -> bool:
        """Return True if the given model supports tool calling."""
```

### ProviderCapabilities

A frozen dataclass returned by `get_capabilities()`:

```python
@dataclass(frozen=True)
class ProviderCapabilities:
    supports_image: bool = False
    supports_video: bool = False
    supports_llm: bool = False
    supports_model_sync: bool = False
    capabilities: list[ModelCapability] = field(default_factory=list)
```

The `capabilities` list holds granular `ModelCapability` enum values (from
`app/services/model_capabilities.py`) that describe exactly what a provider's
models can do - text-to-image, image-to-image, image-to-video, etc.

Example:

```python
from app.services.model_capabilities import ModelCapability

def get_capabilities(self) -> ProviderCapabilities:
    return ProviderCapabilities(
        supports_image=True,
        supports_video=True,
        supports_llm=False,
        supports_model_sync=True,
        capabilities=[
            ModelCapability.TEXT_TO_IMAGE,
            ModelCapability.IMAGE_TO_IMAGE,
            ModelCapability.IMAGE_TO_VIDEO,
        ],
    )
```

The core system uses these flags to route requests without knowing the
concrete provider type.

### Handling Reference Images (img2img / I2V)

Both `generate_image()` and `generate_video()` accept optional reference
images through `**kwargs`. The pipeline passes these through automatically
when avatars are configured.

**Image-to-Image (img2img)** — `generate_image()` kwargs:

```python
async def generate_image(
    self, prompt: str, model: str, aspect_ratio: str, **kwargs: Any,
) -> tuple[str, bytes]:
    image_path: str | None = kwargs.get("image_path")
    reference_strength: float = kwargs.get("reference_image_strength", 0.75)

    if image_path:
        # Load the reference image and include it in your workflow/payload
        with open(image_path, "rb") as f:
            reference_bytes = f.read()
        # Use reference_bytes + reference_strength to guide generation
```

| Kwarg | Type | Default | Purpose |
|---|---|---|---|
| `image_path` | `str \| None` | `None` | Filesystem path to the reference image for img2img |
| `reference_image_strength` | `float` | `0.75` | How strongly the reference influences output (0.0-1.0) |

**Image-to-Video (I2V)** — `generate_video()` kwargs:

```python
async def generate_video(
    self, prompt: str, model: str, duration: int,
    aspect_ratio: str, **kwargs: Any,
) -> tuple[str, bytes]:
    reference_image_path: str | None = kwargs.get("reference_image_path")

    if reference_image_path:
        # Load the seed image and use it as first frame reference
        with open(reference_image_path, "rb") as f:
            seed_bytes = f.read()
```

| Kwarg | Type | Default | Purpose |
|---|---|---|---|
| `reference_image_path` | `str \| None` | `None` | Filesystem path to the seed image for I2V |

**img2img → T2I fallback**: When `generate_images()` passes a reference image
and the provider call fails (all retries exhausted), the pipeline
automatically retries without the reference image (pure text-to-image). Your
provider does not need to handle this fallback — it just needs to accept the
`image_path` kwarg when provided.

### Model Capability Metadata

Provider `sync_models()` implementations should return capability flags in
each model dict to enable capability-aware routing:

```python
async def sync_models(self) -> list[dict[str, Any]]:
    models = await self._fetch_models()
    return [
        {
            "model_id": m["id"],
            "provider_model_id": m["id"],
            "display_name": m.get("name", m["id"]),
            "modality": "image",
            "capabilities": {
                "accepts_text": True,
                "accepts_image": True,
                "outputs_image": True,
                # outputs_video, etc.
            },
        }
        for m in models
    ]
```

The `capabilities` dict is stored as JSONB in `ModelConfig.capabilities` and
normalized into a `ModelCapabilities` struct by
`normalize_capabilities()` from `app/services/model_capabilities.py`.

**New models default to disabled**: Any model discovered via `sync_models()`
is created with `is_active=False`. An admin must explicitly enable it on the
Model Management page (`/admin/models`) before it can be used. This prevents
unvetted models from appearing in user-facing model selectors.

## Error Classification

Providers map external exceptions to a typed hierarchy via
`classify_error()`:

```python
class ProviderError(Exception):           # Base error
class ProviderOverloadedError(ProviderError):   # Overloaded / at capacity
class ProviderRateLimitError(ProviderError):    # Rate limited (429)
class ProviderConnectionError(ProviderError):   # Connectivity failure
class ProviderTimeoutError(ProviderError):      # Operation timed out
```

The base class provides a default implementation that matches common error
substrings against `_ERROR_PATTERNS`. Subclasses can extend the pattern list
with provider-specific strings:

```python
class MyProvider(ImageProvider, VideoProvider):
    _ERROR_PATTERNS: list[tuple[tuple[str, ...], type[ProviderError]]] = [
        (("overloaded", "capacity", "queue is full"), ProviderOverloadedError),
        (("rate limit", "429"), ProviderRateLimitError),
        (("cold start", "warming up"), ProviderTimeoutError),
        (("connection", "connectionerror"), ProviderConnectionError),
    ]
```

Override `classify_error()` entirely for custom logic. See
`OllamaProvider.classify_error()` for an example of a provider that checks
Ollama-specific conditions before falling back to the base class pattern
matcher.

## ProviderRegistry

The registry maps provider type strings to classes and handles
instantiation. It replaces the old `get_provider_instance()` factory
function.

```python
from app.services.providers import registry

# Register a class
registry.register("your_type", YourProvider)

# Create an instance (calls initialize())
instance = await registry.create("your_type", provider_id, config)

# Look up a class
cls = registry.get("your_type")

# Check if registered
if registry.has("your_type"): ...

# List all registered types
for t in registry.list_types(): ...
```

## Step-by-Step: Adding a New Provider

### 1. Create the Provider Class

Create `backend/app/services/providers/your_provider.py`. Extend
`ProviderBase` and mix in the capability interfaces your provider supports.

```python
from typing import Any
from uuid import UUID

from app.services.model_capabilities import ModelCapability
from app.services.providers.base import (
    ImageProvider,
    VideoProvider,
    ProviderBase,
    ProviderCapabilities,
    ProviderInfo,
)


class YourProvider(ImageProvider, VideoProvider):
    """Provider implementation for [Your Service]."""

    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.example.com/v1")

    async def initialize(self, config: dict) -> None:
        if not self.api_key:
            raise ValueError("api_key is required")

    async def shutdown(self) -> None:
        pass

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(
            name="your_provider",
            provider_type="your_type",
            is_available=True,
            estimated_wait_seconds=30,
            cost_per_job=0.0,
            message="Ready",
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_image=True,
            supports_video=True,
            supports_llm=False,
            supports_model_sync=True,
            capabilities=[
                ModelCapability.TEXT_TO_IMAGE,
                ModelCapability.IMAGE_TO_IMAGE,
                ModelCapability.IMAGE_TO_VIDEO,
            ],
        )

    async def generate_image(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str = "3:2",
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        # Look up model config -- never hardcode model names
        config = await self._get_model_config(model)
        if not config:
            raise ValueError(f"Unknown model: {model}")

        # build_payload handles parameter_map, prompt_format, extra_params
        payload = config.build_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
        )

        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/images/generations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            # Adapt to your API's response format
            image_url = data.get("data", [{}])[0].get("url", "")
            if image_url:
                img_resp = await client.get(image_url)
                return data.get("id", ""), img_resp.content
            return data.get("id", ""), b""

    async def generate_video(
        self,
        prompt: str,
        model: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        # Implement polling pattern for async video generation APIs
        ...

    async def _get_model_config(self, model: str):
        """Resolve a ModelConfig for the given model ID on this provider."""
        from app.database import async_session
        from app.services.model_config_service import ModelConfigService

        async with async_session() as db:
            return await ModelConfigService.get_by_id(
                db, model_id=model, provider_id=self.provider_id
            )
```

### Using ModelConfigService

All model-specific behavior (parameter names, prompt format, API endpoint
selection, duration limits, resolution constraints) lives in the
`model_configs` database table. Your provider code should NEVER hardcode
model name checks. Instead:

```python
config = await self._get_model_config(model)
if not config:
    raise ValueError(f"Unknown model: {model}")

# Build the API payload -- parameter_map handles name translation,
# prompt_format handles string vs array, extra_params adds defaults
payload = config.build_payload(
    prompt=prompt,
    aspect_ratio=aspect_ratio,
)
```

The `build_payload()` method handles:

- **parameter_map**: Translates your param names to provider's param names.
  e.g., `{"aspect_ratio": "aspect", "duration": "seconds"}` means your code
  sends `aspect_ratio="16:9"` and `build_payload()` converts it to
  `aspect: "16:9"` in the API call.
- **prompt_format**: `"string"` sends `{"prompt": "text"}`; `"array"` sends
  `{"prompt": ["text"]}`
- **extra_params**: Provider-specific defaults always included.
  e.g., `{"resolution": "1080p"}` for models that require it.
- **constraints**: Not applied automatically, but available via
  `config.constraints` for your code to validate inputs (e.g.,
  `max_duration_sec`, `supported_ratios`).

### Model Config Fields Reference

| Field | Type | Purpose |
|---|---|---|
| `model_id` | string | Your internal model ID (e.g., "wan2.2") |
| `provider_model_id` | string | Provider's native model ID (e.g., "google/veo3.1-fast/text-to-video") |
| `prompt_format` | "string" or "array" | How the provider expects the prompt |
| `endpoint_type` | string | Which API endpoint to use (generateImage, chat_completions, etc.) |
| `parameter_map` | JSON | Maps your parameter names to provider's parameter names |
| `extra_params` | JSON | Additional params always sent with every request |
| `capabilities` | JSON | Boolean flags: supports_t2v, supports_i2v, supports_image, etc. |
| `constraints` | JSON | Limits: max_duration_sec, supported_ratios, sub_clip_chain |
| `cost_config` | JSON | Pricing: credits_per_image, credits_per_second |

### 2. Register in the Registry

Edit `backend/app/services/providers/__init__.py`:

```python
from app.services.providers.registry import ProviderRegistry
from app.services.providers.your_provider import YourProvider

registry = ProviderRegistry()
# ... existing registrations
registry.register("your_type", YourProvider)
```

The registry is the single entry point for all provider discovery. No
changes are needed in `media_generator.py` or any core service code.

### 3. Add Provider to the Database

Via the UI (Admin, Providers, Add) or directly:

```python
from app.database import Provider

provider = Provider(
    name="My AI Service",
    provider_type="your_type",
    is_active=True,
    config={
        "api_key": "sk-...",
        "base_url": "https://api.example.com/v1",
        "default_image_model": "model-id",
        "default_video_model": "model-id",
    },
)
db.add(provider)
```

### 4. Configure Model Configs

Populate the `model_configs` table for your provider's models:

- Via Admin UI, Model Management, "Add Model" or "Sync"
- Via the provider's `sync_models()` method if it supports dynamic discovery

Each model needs: `model_id`, `provider_model_id`, `display_name`,
`modality`, `endpoint_type`, `prompt_format`, `parameter_map`,
`capabilities`, `constraints`.

### 5. Add Sync Task (Optional)

If your provider supports model sync, add a sync function in
`backend/app/workers/tasks.py`:

```python
async def _sync_yourprovider_models(provider) -> list[dict]:
    instance = YourProvider(provider.id, provider.config)
    await instance.initialize(provider.config)
    try:
        resp = await instance.client.get(
            "https://api.example.com/v1/models",
            headers={"Authorization": f"Bearer {instance.api_key}"},
        )
        models = resp.json().get("data", [])
        return [
            {
                "model_id": m["id"],
                "provider_model_id": m["id"],
                "display_name": m["name"],
                "modality": m.get("type", "image"),
                "endpoint_type": "generateImage",
            }
            for m in models
        ]
    finally:
        await instance.shutdown()
```

Then add an `elif` branch in `_discover_provider_models()` and a cron entry
in the Celery beat schedule.

### 6. Write Tests

Write unit tests that exercise the capability interfaces directly:

```python
import pytest
from uuid import uuid4
from your_provider import YourProvider


@pytest.mark.asyncio
async def test_generate_image():
    provider = YourProvider(uuid4(), {"api_key": "test-key"})
    await provider.initialize({"api_key": "test-key"})
    try:
        asset_id, image_bytes = await provider.generate_image(
            prompt="A cat",
            model="test-model",
            aspect_ratio="1:1",
        )
        assert asset_id
        assert image_bytes
    finally:
        await provider.shutdown()


@pytest.mark.asyncio
async def test_get_status():
    provider = YourProvider(uuid4(), {"api_key": "test-key"})
    await provider.initialize({"api_key": "test-key"})
    try:
        status = await provider.get_status()
        assert status.provider_type == "your_type"
    finally:
        await provider.shutdown()


@pytest.mark.asyncio
async def test_get_capabilities():
    provider = YourProvider(uuid4(), {"api_key": "test-key"})
    caps = provider.get_capabilities()
    assert caps.supports_image
    assert not caps.supports_llm
```

## ComfyUI-Based Providers

Providers that use ComfyUI workflows (ComfyUIDirectProvider,
RunPodProvider) share a common module at `providers/comfyui/`:

- **`workflow_builders.py`**: Functions to construct ComfyUI workflows:
  - `build_wan_video_workflow()` — Wan2.2 text-to-video
  - `build_wan_i2v_workflow()` — Wan2.2 image-to-video
  - `build_ltx_workflow()` — LTX video generation
  - `upload_image_to_comfyui()` — Upload seed images to ComfyUI input dir
  - `video_generation_resolution()` — Resolve width/height from aspect ratio

- **`workflows/`**: Static JSON workflow files (wan_s2v.json,
  flux_image.json, ltx_t2v.json, ltx_i2v.json)

These providers extend `ComfyUIProvider` (alongside the capability
interfaces) to maintain compatibility with the workflow-based system. The
legacy `queue_prompt()`, `wait_for_completion()`, and `get_output()` methods
are used internally by the provider's `generate_image()` /
`generate_video()` implementations and are not part of the public
capability contract.

## Provider Config Reference

The `config` JSON column on the `providers` table stores provider-specific
settings. Common keys:

| Key | Used By | Description |
|---|---|---|
| `api_key` | Poe, AtlasCloud, custom | API authentication key |
| `base_url` | Ollama, custom | API base URL |
| `comfyui_url` | comfyui_direct | ComfyUI server URL |
| `endpoint_id` | runpod | RunPod serverless endpoint ID |
| `max_concurrent_jobs` | comfyui_direct | Max parallel ComfyUI jobs |
| `wan_unet_name` | comfyui_direct | Wan model filename |
| `wan_clip_name` | comfyui_direct | CLIP model filename |
| `wan_vae_name` | comfyui_direct | VAE model filename |
| `wan_video_steps` | comfyui_direct | Sampling steps for video |
| `wan_video_cfg` | comfyui_direct | CFG scale for video |
| `wan_video_fps` | comfyui_direct | Output FPS for video |
| `default_model` | Ollama | Default LLM model name |
| `cost_per_gpu_hour` | runpod | GPU cost for duration estimates |
| `idle_timeout_seconds` | runpod | Timeout for cold start detection |

## Testing Your Provider

1. Create a provider via the Admin UI
2. Set model preferences in Settings, AI Models
3. Create a job and trigger image/video generation
4. Check worker logs: `docker compose logs worker -f | grep your_type`
5. Verify output files in the storage directory

The core system discovers providers through the registry. Once registered,
all routing is automatic based on the provider type selected in the user's
model preferences. No changes to routing code are needed.
