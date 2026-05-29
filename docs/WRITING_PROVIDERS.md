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
| `atlascloud` | `AtlasCloudProvider` | AtlasCloud API (300+ models: Flux, Kling, WAN, Veo, etc.) |

## Step-by-Step: Adding a New Provider

### Provider Registration Checklist

When adding a new provider, complete ALL of these steps:

1. **Create provider class** — `backend/app/services/providers/your_provider.py`
   - Extend `ComfyUIProvider` from `providers/base.py`
   - Implement `initialize(config)`
   - Implement `generate_image(prompt, model, ...)` and/or `generate_video(prompt, model, ...)`

2. **Register in factory** — `backend/app/services/media_generator.py`
   - Add your provider type to `get_provider_instance()` — map type string to class
   - Import your class in the function

3. **Add database record** — via Admin UI or migration
   - Provider type must match the string registered in step 2
   - Config JSON: `{"api_key": "...", "base_url": "..."}`

4. **Configure model configs** — populate `model_configs` table for your provider's models
   - Via Admin UI to Model Management to "Add Model" or "Sync"
   - Each model needs: `model_id`, `provider_model_id`, `display_name`, `modality`, `endpoint_type`, `prompt_format`, `parameter_map`, `capabilities`, `constraints`

5. **Use ModelConfigService in provider code** — all model-specific behavior comes from config, not hardcoded checks
   - See section "Using ModelConfigService" below

6. **Add frontend model selection** — optional, for user-facing model dropdowns
   - Models with `is_active=true` automatically appear in model selection dropdowns

7. **Add sync task** — `backend/app/workers/tasks.py`
   - Create `_sync_yourprovider_models(provider)` function returning `list[dict]`
   - Each dict: `model_id`, `provider_model_id`, `display_name`, `modality`, `endpoint_type`
   - Add `elif` branch in `_discover_provider_models()` to route your provider type
   - Add to Celery beat schedule in `celery_app.py`
   - Use `model_normalizer.py` to translate provider API metadata — never hardcode modality
   - Reference: see `_sync_atlascloud_models()` and `_sync_poe_models()` in `tasks.py`

### Model Normalization

All sync functions MUST use `backend/app/services/model_normalizer.py` to convert raw
provider API responses into our standard `model_configs` format.

```python
from app.services.model_normalizer import normalize_provider_model

async def _sync_yourprovider_models(provider) -> list[dict]:
    instance = YourProvider(provider.id, provider.config)
    await instance.initialize(provider.config)
    try:
        resp = await instance.client.get("https://api.example.com/v1/models",
            headers={"Authorization": f"Bearer {instance.api_key}"})
        return [normalize_provider_model("your_type", m) for m in resp.json().get("data", [])]
    finally:
        await instance.shutdown()
```

Add a `_normalize_yourprovider()` function in `model_normalizer.py` and register it in
`normalize_provider_model()`. Map the provider's native fields:
- `modality` — from provider's own classification (type field, output_modalities)
- `endpoint_type` — `"chat_completions"`, `"generateImage"`, or `"generateVideo"`
- `capabilities` — optional: `accepts_image`, `supports_tools`, etc.
- `constraints` — optional: `context_length`, `max_output_tokens`
- `cost_config` — optional: `currency`, `credits_per_image`

### Sync Registration Checklist
1. `_discover_provider_models()` in `tasks.py` — add `elif` branch
2. `normalize_provider_model()` in `model_normalizer.py` — add normalization function
3. Celery beat schedule in `celery_app.py` — add cron entry

8. **Write tests** — TDD as usual
   - Unit tests for provider class
   - Integration tests for model config + payload construction

### 1. Create the Provider Class

Create `backend/app/services/providers/your_provider.py`:

```python
import asyncio
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.database import ModelConfig
from app.services.model_config_service import ModelConfigService
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

    async def _get_model_config(self, model: str) -> ModelConfig | None:
        """Resolve a ModelConfig for the given model ID on this provider."""
        from app.database import async_session

        async with async_session() as db:
            return await ModelConfigService.get_by_id(
                db, model_id=model, provider_id=self.provider_id
            )

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
        # Look up model config — never hardcode model names
        config = await self._get_model_config(model)
        if not config:
            raise ValueError(f"Unknown model for this provider: {model}")

        # build_payload handles parameter_map, prompt_format, extra_params
        payload = config.build_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
        )
        if quality:
            payload["quality"] = quality

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

### Using ModelConfigService

All model-specific behavior (parameter names, prompt format, API endpoint selection,
duration limits, resolution constraints) lives in the `model_configs` database table.
Your provider code should NEVER hardcode model name checks. Instead:

```python
from app.services.model_config_service import ModelConfigService

class YourProvider(ComfyUIProvider):
    async def generate_image(self, prompt, model, aspect_ratio="3:2", ...):
        # Get model configuration from database
        config = await self._get_model_config(model)
        if not config:
            raise ValueError(f"Unknown model: {model}")

        # Build the API payload — parameter_map handles name translation,
        # prompt_format handles string vs array, extra_params adds defaults
        payload = config.build_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
        )
        # payload is now: {"model": "provider/model-id", "prompt": "...", "aspect": "16:9", ...}

        # Submit to your provider's API
        response = await self.client.post(f"{self.base_url}/generate", json=payload)
        ...

    async def _get_model_config(self, model: str):
        """Look up model configuration from database."""
        from app.database import async_session

        async with async_session() as db:
            return await ModelConfigService.get_by_id(
                db, model_id=model, provider_id=self.provider_id
            )
```

The `build_payload()` method handles:

- **parameter_map**: Translates your param names to provider's param names.
  e.g., `{"aspect_ratio": "aspect", "duration": "seconds"}` means your code sends
  `aspect_ratio="16:9"` and `build_payload()` converts it to `aspect: "16:9"` in the API call.
- **prompt_format**: `"string"` sends `{"prompt": "text"}`; `"array"` sends `{"prompt": ["text"]}`
- **extra_params**: Provider-specific defaults always included.
  e.g., `{"resolution": "1080p"}` for models that require it.
- **constraints**: Not applied automatically, but available via `config.constraints`
  for your code to validate inputs (e.g., `max_duration_sec`, `supported_ratios`).

### Model Config Fields Reference

| Field | Type | Purpose |
|-------|------|---------|
| `model_id` | string | Your internal model ID (e.g., "wan2.2") |
| `provider_model_id` | string | Provider's native model ID (e.g., "google/veo3.1-fast/text-to-video") |
| `prompt_format` | "string" or "array" | How the provider expects the prompt |
| `endpoint_type` | string | Which API endpoint to use (generateImage, chat_completions, etc.) |
| `parameter_map` | JSON | Maps your parameter names to provider's parameter names |
| `extra_params` | JSON | Additional params always sent with every request |
| `capabilities` | JSON | Boolean flags: supports_t2v, supports_i2v, supports_image, etc. |
| `constraints` | JSON | Limits: max_duration_sec, supported_ratios, sub_clip_chain |
| `cost_config` | JSON | Pricing: credits_per_image, credits_per_second |

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
