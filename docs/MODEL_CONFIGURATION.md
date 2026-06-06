# Model Configuration System

This document describes how VidForge manages AI model configurations — from database schema and provider registration to model resolution, normalization, and frontend consumption.

## Table of Contents

- [Overview](#overview)
- [Database Schema](#database-schema)
- [Provider Types](#provider-types)
- [ModelConfig Fields](#modelconfig-fields)
- [Model Resolution](#model-resolution)
- [Model Normalization & Sync](#model-normalization--sync)
- [API Endpoints](#api-endpoints)
- [Frontend Integration](#frontend-integration)
- [Default Preferences](#default-preferences)
- [Cost Configuration](#cost-configuration)
- [Constraints & Capabilities](#constraints--capabilities)
- [Adding New Models](#adding-new-models)

---

## Overview

VidForge's model configuration system is built around two core database tables:

- **`providers`** — AI backend instances (ComfyUI, Poe, RunPod, AtlasCloud, Ollama)
- **`model_configs`** — Individual model configurations linked to a provider

A `ModelConfig` row defines everything needed to invoke a specific model: its canonical ID, provider-specific ID, modality (image/video/text), capabilities, constraints, cost, and parameter mapping.

The system supports:

- **Multiple providers** of the same type (e.g., two ComfyUI instances)
- **Model families** that resolve to task-specific variants (e.g., `wan2.2` → `wan2.2_i2v` when a seed image is present)
- **Legacy model ID resolution** for backward compatibility with old job data
- **Automatic model discovery** via provider APIs with normalization
- **User-specific model preferences** with granular per-task overrides

---

## Database Schema

### Provider

```python
class Provider(Base):
    id: UUID              # Primary key
    name: str             # Human-readable name (unique)
    provider_type: str    # "comfyui_direct" | "poe" | "runpod" | "atlascloud" | "ollama"
    config: dict          # Provider-specific JSON configuration
    is_active: bool       # Whether the provider is enabled
    daily_budget_limit: Decimal | None
    current_daily_spend: Decimal
    priority: int         # Routing priority (lower = higher priority)
```

Each provider type has a distinct `config` schema:

| Type | Config Fields |
|------|---------------|
| `comfyui_direct` | `comfyui_url`, `max_concurrent_jobs` |
| `poe` | `api_key`, `max_concurrent_jobs`, `default_video_model`, `default_image_model` |
| `runpod` | `api_key`, `endpoint_id`, `cost_per_gpu_hour`, `idle_timeout_seconds`, `flashboot_enabled`, `max_workers` |
| `atlascloud` | `api_key` |
| `ollama` | (inferred from provider type) |

Providers are managed via the Admin UI or the `/api/providers` endpoints.

### ModelConfig

```python
class ModelConfig(Base):
    id: UUID                  # Primary key
    provider_id: UUID         # FK → providers.id
    model_id: str             # Canonical ID (unique per provider)
    provider_model_id: str    # Provider's native model identifier
    display_name: str         # Human-readable name
    modality: str             # "image" | "video" | "text"
    prompt_format: str        # "string" | "array"
    endpoint_type: str        # "llm" | "text_to_image" | "image_to_video" | "text_to_video" | "image" | "video"
    parameter_map: dict | None    # Key translation: our params → provider's params
    extra_params: dict | None     # Provider-specific defaults
    capabilities: dict | None   # accepts_image, outputs_video, etc.
    constraints: dict | None      # max_duration, max_resolution, resolutions, size_param_family, etc.
    cost_config: dict | None      # Cost metadata
    comfyui_workflow: str | None  # Workflow file name (for ComfyUI providers)
    extra_config: dict | None     # Provider-specific metadata (was in separate per-provider tables)
    is_active: bool
    is_deprecated: bool
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

Unique constraint: `(provider_id, model_id)`.

### Job

The `Job` model stores per-generation provider and model selections:

```python
class Job(Base):
    provider_id: UUID | None          # FK → providers.id (main provider)
    image_provider_id: UUID | None    # FK → providers.id (image generation)
    video_provider_id: UUID | None    # FK → providers.id (video generation)
    provider_type: str | None         # Cached provider type at creation
    model_preference: str | None      # Optional model override
    estimated_cost: Decimal | None  # Pre-generation cost estimate
    actual_cost: Decimal | None       # Post-generation actual cost
```

When a job is created, the system resolves the user's preferred model + provider and stores the provider IDs directly on the job. This ensures the job continues to use the same provider even if the user's preferences change later.

### UserSettings

```python
class UserSettings(Base):
    user_id: UUID         # FK → users.id (PK)
    preferences: dict     # JSON blob with model preferences
```

The `preferences` dict stores per-user model selections:

```json
{
  "image_model": "flux1-schnell",
  "video_model": "wan2.2",
  "text_model": "qwen3.6:35b",
  "text_to_image_model": "flux1-schnell",
  "image_to_video_model": "wan2.2",
  ...
}
```

---

## Provider Types

| Type | Class | Description |
|------|-------|-------------|
| `comfyui_direct` | `ComfyUIDirectProvider` | Local ComfyUI via HTTP API |
| `poe` | `PoeProvider` | Poe API (Veo, GPT-Image, Wan, Sora, etc.) |
| `runpod` | `RunPodProvider` | RunPod serverless ComfyUI endpoints |
| `atlascloud` | `AtlasCloudProvider` | AtlasCloud API (300+ models) |
| `ollama` | `OllamaProvider` | Local Ollama LLM server |

Provider classes extend `ComfyUIProvider` (or implement `generate_image`/`generate_video` directly) and are instantiated via `get_provider_instance()` in `media_generator.py`.

---

## ModelConfig Fields

### `model_id` vs `provider_model_id`

- **`model_id`** — The canonical ID used throughout VidForge (e.g., `"flux1-schnell"`, `"wan2.2"`).
- **`provider_model_id`** — The provider's native identifier (e.g., `"GPT-Image-1"` for Poe, `"wan2.2_t2v"` for ComfyUI).

This separation allows the same canonical model to be backed by different providers with different native IDs.

### `parameter_map`

Translates VidForge parameter names to provider-specific names:

```json
{
  "prompt": "text",
  "negative_prompt": "negative_text",
  "seed": "seed"
}
```

When `build_payload()` is called, each key in `kwargs` is looked up in `parameter_map` and translated before being sent to the provider.

### `prompt_format`

- `"string"` — Prompt is sent as a single string (default).
- `"array"` — Prompt is wrapped in a list: `["prompt text"]`.

### `extra_params`

Provider-specific default parameters merged into the payload:

```json
{
  "aspect_ratio": "1:1",
  "num_inference_steps": 30
}
```

### `capabilities`

A dict of booleans describing what the model can do:

```json
{
  "accepts_text": true,
  "accepts_image": true,
  "outputs_video": true
}
```

If `capabilities` is not provided, it is inferred from `modality`:
- `image` → `{"accepts_text": true, "outputs_image": true}`
- `video` → `{"accepts_text": true, "outputs_video": true}`
- `text` → `{"accepts_text": true, "outputs_text": true}`

---

## Model Resolution

### ModelConfigService

`ModelConfigService` is the single source of truth for resolving a model reference to an active `ModelConfig` row.

**Resolution order** (`resolve_model_config()`):

1. **Exact `model_id`** match (preferred)
2. **Exact `provider_model_id`** match
3. **Legacy prefix stripping** — handles old provider-prefixed IDs like `"poe/flux1-schnell"` or `"atlascloud/flux1-schnell"`
4. **AtlasCloud repair** — prepends `"atlascloud/"` to bare IDs for AtlasCloud context
5. **Unique suffix match** — finds a model whose `model_id` ends with `/{stripped}`

Each step logs a warning if a legacy resolution occurs, helping migrate old data.

### Model Resolver (Family Variants)

Some models are organized into **families** that share a base ID but have task-specific variants:

```python
_FAMILY_VARIANT_MAP = {
    "wan2.2": {
        (True, False): "wan2.2_i2v",   # has seed image
        (False, True): "wan2.2_s2v",   # scene continuation
        (False, False): "wan2.2_t2v",  # text-to-video
    },
    "ltx2.3": {
        (True, False): "ltx2.3_i2v",
        (False, False): "ltx2.3_t2v",
    },
    "ltx2.3-fast": {
        (False, False): "ltx2.3_distilled",
    },
}
```

`resolve_model_variant(family_id, has_seed_image, is_scene_continuation)` selects the correct variant based on job context.

**Legacy mapping** ensures old variant IDs (e.g., `"wan2.2-t2v"`) are mapped back to the family ID `"wan2.2"` before resolution.

---

## Model Normalization & Sync

### Normalization

Each provider is responsible for normalizing its own models. The provider class implements a `sync_models()` method that returns a list of normalized model dicts. This replaces the old centralized approach where a separate `model_normalizer.py` handled per-provider normalization.

```python
class YourProvider(ProviderBase, ImageProvider):
    async def sync_models(self) -> list[dict]:
        # Fetch models from provider API
        raw_models = await self._fetch_model_list()
        # Normalize each model into a standard dict
        return [
            {
                "model_id": canonical_id,
                "provider_model_id": provider_native_id,
                "display_name": friendly_name,
                "modality": inferred_modality,
                "endpoint_type": endpoint_category,
                "capabilities": {...},
                "cost_config": {...},
            }
            for raw in raw_models
        ]
```

**Example: AtlasCloud normalization**

AtlasCloud model IDs follow the pattern `{provider}/{family}/{task-type}` (e.g., `"kling/text-to-video"`). The provider's `sync_models()` method parses the task-type suffix to infer capabilities:
- `/i2v` or `image-to-video` → `accepts_image: true, outputs_video: true`
- `/t2v` or `text-to-video` → `accepts_text: true, outputs_video: true`
- `/v2v` or `video-to-video` → `accepts_video: true, outputs_video: true`

### Sync Flow

Model synchronization can be triggered on demand or run periodically:

1. **On-demand**: `POST /api/providers/{provider_id}/sync-models` (admin)
2. **Manual trigger**: Admin UI → Model Management → Sync button

The sync flow works as follows:

1. The endpoint creates a provider instance via `registry.create(provider_type, id, config)`
2. Calls `instance.sync_models()` on the provider instance
3. Each returned model dict is upserted via `ModelConfigService.get_or_create()`
4. The `extra_config` column stores provider-specific metadata that was previously kept in separate per-provider tables

Providers currently supporting auto-sync:
- **AtlasCloud** — full catalog via API
- **Poe** — bot list via API

Add sync support for a new provider by:
1. Implementing `sync_models()` on your provider class (return a list of normalized dicts)
2. Registering the provider type in the provider registry
3. (Optional) Adding a Celery beat schedule in `celery_app.py`

---

## API Endpoints

### Models

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/models/available` | List all active models grouped by modality (image/video/text) |
| `GET` | `/models/preferences` | Get current user's model preferences |
| `PUT` | `/models/preferences` | Update user's model preferences |

### Providers (Admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/providers` | List all providers |
| `POST` | `/providers` | Create a new provider |
| `PATCH` | `/providers/{id}` | Update a provider |
| `DELETE` | `/providers/{id}` | Delete a provider |
| `GET` | `/providers/{id}/status` | Check provider health and queue status |

### Provider Model Configs (Admin)

Generic model CRUD endpoints work the same for all provider types. The `model_configs` table holds all models in a single table — there are no separate per-provider model tables.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/providers/{provider_id}/models` | List all model configs for a provider |
| `POST` | `/providers/{provider_id}/models` | Create a model config |
| `PATCH` | `/providers/{provider_id}/models/{model_id}` | Update a model config |
| `DELETE` | `/providers/{provider_id}/models/{model_id}` | Soft-delete (deactivate) a model config |
| `POST` | `/providers/{provider_id}/sync-models` | Sync live provider models into local configs |

---

## Frontend Integration

### API Client

The frontend consumes model configuration via `modelsApi` in `frontend/src/api/client.ts`:

```typescript
export const modelsApi = {
  getAvailableModels: async () => {
    const response = await api.get<{
      image_models: ModelConfig[];
      video_models: ModelConfig[];
      text_models: ModelConfig[];
    }>('/models/available')
    return response.data
  },

  getModelPreferences: async () => {
    const response = await api.get<ModelPreferences>('/models/preferences')
    return response.data
  },

  updateModelPreferences: async (prefs: ModelPreferences) => {
    const response = await api.put<ModelPreferences>('/models/preferences', prefs)
    return response.data
  },
}
```

### TypeScript Types

```typescript
export interface ModelConfig {
  id: string
  name: string
  display_name?: string
  description: string
  size_gb: number
  speed: string
  quality: string
  license: string
  provider: string
  provider_id?: string
  default: boolean
  capabilities?: Record<string, boolean>
  cost_config?: Record<string, unknown> | null
  resolutions?: string[] | null
  size_param_family?: string | null
  variants?: Record<string, { workflow: string; description: string }>
}

export interface ModelPreferences {
  image_model: string
  video_model: string
  text_model: string
  image_provider: string
  video_provider: string
  text_provider: string
  text_to_image_model: string
  image_to_image_model: string
  text_to_video_model: string
  image_to_video_model: string
  image_provider_id: string
  video_provider_id: string
  text_provider_id: string
  text_to_image_provider_id: string
  image_to_image_provider_id: string
  text_to_video_provider_id: string
  image_to_video_provider_id: string
}
```

### Admin Model Management

The `ModelManagement.tsx` admin page provides a full CRUD interface for `model_configs`:
- Create/edit model configs with JSON fields (capabilities, constraints, cost_config, parameter_map, extra_params)
- Toggle `is_active` status
- Trigger provider sync
- Filter by provider, modality, and search query

---

## Default Preferences

When a new user is created or preferences are reset, the system applies defaults defined in `backend/app/api/models.py`:

```python
_DEFAULT_MODEL_VALUES = {
    "image_model": "flux1-schnell",
    "video_model": "wan2.2",
    "text_model": "qwen3.6:35b",
    "image_provider": "local",
    "video_provider": "local",
    "text_provider": "local",
    "text_to_image_model": "flux1-schnell",
    "image_to_image_model": "flux1-schnell",
    "text_to_video_model": "wan2.2",
    "image_to_video_model": "wan2.2",
}
```

Provider IDs are looked up at runtime:
- Image/video provider ID → first active `comfyui_direct` provider
- Text provider ID → first active `ollama` provider

These defaults ensure new users can generate media immediately without manual configuration.

---

## Cost Configuration

The `cost_config` JSON field tracks pricing metadata per model:

```json
{
  "cost": 0,
  "credits_per_image": 1,
  "credits_per_second": 0.5,
  "compute_points": 10,
  "currency": "credits"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `cost` | `number` | Flat cost flag (0 = free/local) |
| `credits_per_image` | `number` | Cost per image generation |
| `credits_per_second` | `number` | Cost per second of video |
| `compute_points` | `number` | Alternative cost metric |
| `currency` | `string` | Display unit (e.g., `"credits"`) |

The frontend's `QuickCreateMedia` component uses `cost_config` to display estimated costs:

```typescript
function getEstimatedCost() {
  if (!selectedModel?.costConfig) return null
  const cc = selectedModel.costConfig
  if (cc.cost === 0) return 'Free (local)'
  const credits = cc.credits_per_image || cc.credits_per_second || cc.compute_points || 0
  const total = credits * duration
  return `~${total} ${cc.currency || 'credits'}`
}
```

---

## Constraints & Capabilities

### Constraints

Stored in the `constraints` JSON field:

| Field | Type | Description |
|-------|------|-------------|
| `max_duration` | `int` | Maximum video duration in seconds |
| `max_resolution` | `string` | Max resolution string (e.g., `"1920x1080"`) |
| `default_steps` | `int` | Default inference steps |
| `distilled` | `bool` | Whether this is a distilled/fast variant |
| `resolutions` | `string[]` | Supported resolution strings |
| `size_param_family` | `string` | Size parameter family: `"ratio"` or `"pixels"` |

**Size Parameter Family**

- `"ratio"` — Models accept aspect ratios like `"16:9"`, `"1:1"` (ComfyUI direct)
- `"pixels"` — Models accept exact pixel dimensions like `"1536x2688"` (Poe, AtlasCloud)

The frontend adapts its UI based on `size_param_family`:
- Ratio-based models show aspect ratio buttons
- Pixel-based models show a resolution dropdown

### Capabilities

Determines which UI options are shown and which provider is selected:

| Capability | Meaning |
|------------|---------|
| `accepts_text` | Model can take text prompts |
| `accepts_image` | Model can take reference/seed images |
| `accepts_video` | Model can take video inputs |
| `outputs_image` | Model generates images |
| `outputs_video` | Model generates videos |
| `outputs_text` | Model generates text |

The `QuickCreateMedia` dialog uses capabilities to filter models by task type (text-to-image, image-to-video, etc.).

---

## Adding New Models

### Via Admin UI

1. Navigate to **Admin → Model Management**
2. Click **Add Model**
3. Fill in required fields:
   - `model_id` — Canonical ID (e.g., `"my-model"`)
   - `provider_model_id` — Provider's native ID
   - `display_name` — Human-readable name
   - `modality` — image/video/text
   - `provider` — Select from active providers
4. Optionally configure:
   - `capabilities` — JSON dict of booleans
   - `constraints` — JSON with resolutions, max_duration, etc.
   - `cost_config` — JSON with pricing
   - `parameter_map` — JSON mapping VidForge params to provider params
   - `extra_params` — JSON with provider-specific defaults

### Via Provider Sync

For providers supporting auto-discovery (AtlasCloud, Poe):

1. Go to **Admin → Model Management**
2. Click **Sync** next to the provider
3. New models are automatically imported with normalized metadata
4. Review and activate imported models as needed

### Via Database Migration

For bulk seeding or environment setup, use an Alembic migration to insert `model_configs` rows:

```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

model_configs = sa.table(
    'model_configs',
    sa.column('id', UUID),
    sa.column('provider_id', UUID),
    sa.column('model_id', sa.String),
    sa.column('provider_model_id', sa.String),
    sa.column('display_name', sa.String),
    sa.column('modality', sa.String),
    sa.column('endpoint_type', sa.String),
    sa.column('capabilities', sa.JSON),
    sa.column('constraints', sa.JSON),
    sa.column('cost_config', sa.JSON),
    sa.column('is_active', sa.Boolean),
)

op.bulk_insert(model_configs, [
    {
        'id': uuid4(),
        'provider_id': provider_id,
        'model_id': 'my-model',
        'provider_model_id': 'provider/MyModel-v1',
        'display_name': 'My Model',
        'modality': 'image',
        'endpoint_type': 'text_to_image',
        'capabilities': {'accepts_text': True, 'outputs_image': True},
        'constraints': {'resolutions': ['1024x1024', '1536x2688']},
        'cost_config': {'credits_per_image': 2, 'currency': 'credits'},
        'is_active': True,
    }
])
```

---

## Related Documentation

- [WRITING_PROVIDERS.md](WRITING_PROVIDERS.md) — Adding new AI providers
- [WRITING_PLUGINS.md](WRITING_PLUGINS.md) — Template plugin development
- [PLUGIN_ARCHITECTURE.md](PLUGIN_ARCHITECTURE.md) — Plugin system overview
- [DEPLOYMENT.md](DEPLOYMENT.md) — Infrastructure and deployment
