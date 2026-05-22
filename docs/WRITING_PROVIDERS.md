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
│  • Extends ComfyUIProvider (in providers/base.py)         │
│  • Implements initialize(), queue_prompt(), etc.          │
│  • Or implements generate_image() / generate_video()     │
│     directly (like PoeProvider)                           │
├──────────────────────────────────────────────────────────┤
│  Provider Type Registry                                   │
│  • get_provider_instance() maps type → class              │
│  • comfyui_direct → ComfyUIDirectProvider                │
│  • poe → PoeProvider                                      │
│  • runpod → RunPodProvider                                │
│  • your_type → YourProvider                               │
└──────────────────────────────────────────────────────────┘
```

## Existing Provider Types

| Type | Class | Description |
|---|---|---|
| `comfyui_direct` | `ComfyUIDirectProvider` | Local ComfyUI instance via HTTP API |
| `poe` | `PoeProvider` | Poe API (Veo, GPT-Image, Wan, Sora, etc.) |
| `runpod` | `RunPodProvider` | RunPod serverless ComfyUI |

## Step-by-Step: Adding a New Provider

### 1. Create the Provider Class

Create `backend/app/services/providers/your_provider.py`:

```python
import asyncio
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.services.providers.base import ComfyUIProvider, ProviderInfo


class YourProvider(ComfyUIProvider):
    """AI provider implementation for [Your Service]."""

    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.example.com/v1")

    async def initialize(self, config: dict) -> None:
        """Called once when the provider is instantiated."""
        if not self.api_key:
            raise ValueError("api_key is required for your_provider")

    # --- Direct generation methods (like Poe) ---

    async def generate_image(
        self,
        prompt: str,
        model: str = "default-model",
        aspect_ratio: str = "3:2",
        quality: str = "high",
        negative_prompt: str = "",
        image_path: str | None = None,
    ) -> tuple[str, bytes | None]:
        """Generate an image. Returns (request_id, image_bytes)."""
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/images/generations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "prompt": prompt,
                    "size": _aspect_to_size(aspect_ratio),
                    "quality": quality,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Adapt to your API's response format
            image_url = data.get("data", [{}])[0].get("url", "")
            if image_url:
                img_resp = await client.get(image_url)
                return data.get("id", ""), img_resp.content
            return data.get("id", ""), None

    async def generate_video(
        self,
        prompt: str,
        model: str = "default-model",
        duration: int = 5,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        negative_prompt: str = "",
        image_path: str | None = None,
    ) -> tuple[str, bytes | None]:
        """Generate a video. Returns (request_id, video_bytes)."""
        # Implement polling pattern for async video generation APIs
        ...

    # --- ComfyUI-style interface (required by base class) ---

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        # Only needed if your provider accepts ComfyUI workflows
        raise NotImplementedError("Use generate_image/generate_video directly")

    async def wait_for_completion(self, job_id: str, **kwargs) -> dict:
        return {"status": "completed", "job_id": job_id}

    async def get_output(self, result: dict) -> bytes | None:
        return result.get("output_data")

    async def cancel_job(self, job_id: str) -> bool:
        return False

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(
            name="your_provider",
            provider_type="your_type",
            is_available=True,
            estimated_wait_seconds=30,
            cost_per_job=0.0,
            message="Ready",
        )

    async def estimate_cost(self, workflow: dict) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict) -> float:
        return 30.0

    async def shutdown(self) -> None:
        pass
```

### 2. Register the Provider Type

Edit `app/services/media_generator.py` — add your type to
`get_provider_instance()`:

```python
async def get_provider_instance(db, provider):
    if provider.provider_type == "your_type":
        from app.services.providers.your_provider import YourProvider
        instance = YourProvider(provider.id, provider.config)
        await instance.initialize(provider.config)
        return instance
    # ... existing types
```

### 3. Add Provider to the Database

Via the UI (Admin → Providers → Add) or directly:

```python
# backend/app/cli.py or a migration
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

### 4. Add Poe-style Model Support (Optional)

If your provider supports multiple models, add them to the `poe_models` table
(or create a new table). The `poe_models` table is provider-agnostic despite
the name — any provider type can use it.

For the frontend model picker to show your models, they need to appear in the
`/api/models/available` endpoint. If your models are in `poe_models` they'll
be auto-included. Otherwise add them to `model_config.py`.

### 5. Route Media Generation to Your Provider

The routing is handled by user preferences. When a user selects your
provider's model in Settings → AI Models, the `_resolve_image_provider()`
and `_resolve_video_provider()` functions in `media_generator.py` detect
the provider prefix and route to your provider class.

For Poe-type providers (direct API calls), models are prefixed with
`poe:` (e.g., `poe:your-model`). For your provider, choose a prefix:

```python
# In _resolve_image_provider / _resolve_video_provider:
if selected_model.startswith("your_prefix:"):
    model_id = selected_model.removeprefix("your_prefix:")
    provider, instance = await _get_provider_by_type(db, "your_type")
    if provider and instance:
        return model_id, provider.id, "your_type", instance
```

## Provider Config Reference

The `config` JSON column on the `providers` table stores provider-specific
settings. Common keys:

| Key | Used By | Description |
|---|---|---|
| `api_key` | Poe, custom | API authentication key |
| `base_url` | Poe, custom | API base URL |
| `comfyui_url` | comfyui_direct | ComfyUI server URL |
| `max_concurrent_jobs` | comfyui_direct | Max parallel ComfyUI jobs |
| `wan_unet_name` | comfyui_direct | Wan model filename |
| `wan_clip_name` | comfyui_direct | CLIP model filename |
| `wan_vae_name` | comfyui_direct | VAE model filename |
| `wan_video_steps` | comfyui_direct | Sampling steps for video |
| `wan_video_cfg` | comfyui_direct | CFG scale for video |
| `wan_video_fps` | comfyui_direct | Output FPS for video |

## Testing Your Provider

1. Create a provider via the Admin UI
2. Set model preferences in Settings → AI Models
3. Create a job and trigger image/video generation
4. Check worker logs: `docker compose logs worker -f | grep your_type`
5. Verify output files in the storage directory

## ComfyUI Workflow Reference

If your provider accepts ComfyUI workflows (like `comfyui_direct` and
`runpod`), you can define custom workflows in JSON files under
`backend/app/comfyui/workflows/`. These are loaded by
`load_comfyui_workflow()` in `media_generator.py`.

Existing workflows:

| File | Purpose |
|---|---|
| `wan_s2v.json` | Wan 2.2 T2V (text-to-video) |
| `flux_image.json` | Flux.1-schnell image generation |
| `ltx_t2v.json` | LTX video generation |
| `ltx_i2v.json` | LTX image-to-video |

For programmatic workflows, use the builder functions:

- `_build_wan_video_workflow()` — T2V video (no seed image)
- `_build_wan_i2v_workflow()` — I2V video (with seed image as first frame)
- `_build_flux_image_workflow()` — Flux image generation
- `_build_comfyui_image_workflow()` — Generic ComfyUI image workflow
