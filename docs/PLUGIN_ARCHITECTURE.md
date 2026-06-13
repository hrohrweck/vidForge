# Plugin Architecture

> **Status**: Implemented. All 6 phases complete.

VidForge uses a plugin system where each template type is a self-contained
Python package with its own scene planning logic, pipeline hooks, and UI
components. The core system provides shared services (image/video generation,
LLM, rendering) and the plugins provide template-specific behavior.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Core System                                        │
│  • Model config (image, video, text models)         │
│  • Scene CRUD (API + DB)                            │
│  • Media generation (capability-based provider interfaces)        │
│  • Video rendering (FFmpeg merge, audio mix)        │
│  • Job lifecycle (dispatcher → plugin stages)       │
│  • Storage backends (local, S3, SSH)                │
├─────────────────────────────────────────────────────┤
│  Plugin Interface (PluginBase ABC)                   │
│  • enrich_inputs()   — pre-process raw inputs,       │
│    auto-create avatars if none selected              │
│  • plan_scenes()     — create VideoScene rows        │
│    (receives model capabilities context)             │
│  • generate_images() — seed images per scene         │
│    (auto-passes avatar ref images for img2img)       │
│  • generate_videos() — video clips per scene         │
│    (auto-passes seed frames for I2V)                 │
│  • render()          — merge + audio + preview       │
├─────────────────────────────────────────────────────┤
│  Plugins (backend/plugins/)                          │
│  • music_video/                                      │
│  • prompt_to_video/                                  │
│  • script_to_video/                                  │
└─────────────────────────────────────────────────────┘
```

## Directory Structure

```
backend/
├── app/plugins/
│   ├── __init__.py              # empty
│   ├── base.py                  # PluginBase ABC
│   └── registry.py              # discover_plugins(), get_plugin(), etc.
├── plugins/                     # actual plugin packages
│   ├── music_video/
│   │   ├── __init__.py          # exports create_plugin()
│   │   ├── plugin.py            # MusicVideoPlugin(PluginBase)
│   │   ├── planner.py           # LLM-based scene planning from lyrics
│   │   ├── lyrics.py            # Whisper-based lyrics extraction
│   │   └── audio_tools.py       # duration, beat detection
│   ├── prompt_to_video/
│   │   ├── __init__.py
│   │   ├── plugin.py            # PromptToVideoPlugin(PluginBase)
│   │   └── planner.py           # LLM-based scene planning from prompt
│   └── script_to_video/
│       ├── __init__.py
│       ├── plugin.py            # ScriptToVideoPlugin(PluginBase)
│       ├── planner.py           # LLM-based scene planning from script
│       ├── script_parser.py     # [bracket annotation] parser
│       └── tts.py               # edge-tts narration generation
frontend/src/
├── pages/
│   ├── SceneEditor.tsx          # Generic scene editor (all plugins)
│   └── editor/                  # Plugin-specific sidebar panels
│       ├── MusicVideoPanel.tsx
│       ├── PromptToVideoPanel.tsx
│       └── ScriptToVideoPanel.tsx
```

## Plugin Base Class

Every plugin extends `PluginBase` (in `app/plugins/base.py`):

```python
class PluginBase(ABC):
    # --- Identity (abstract) ---
    @property
    def plugin_id(self) -> str: ...          # e.g. "music_video"
    @property
    def display_name(self) -> str: ...       # e.g. "Music Video (Scene-Based)"
    @property
    def description(self) -> str: ...

    # --- Template definition (abstract) ---
    def get_template_definition(self) -> dict: ...

    # --- Pipeline stages (overridable, sensible defaults provided) ---
    async def enrich_inputs(self, db, job, context) -> dict: ...
    async def plan_scenes(self, db, job, context) -> dict: ...
    async def generate_images(self, db, job, scenes, context) -> dict: ...
    async def generate_videos(self, db, job, scenes, context) -> dict: ...
    async def render(self, db, job, scenes, context) -> dict: ...

    # --- Per-scene re-render (overridable) ---
    async def rerender_scene_image(self, db, job, scene, context) -> str | None: ...
    async def rerender_scene_video(self, db, job, scene, context) -> str | None: ...

    # --- UI metadata ---
    def get_ui_schema(self) -> dict: ...
    def get_editor_panels(self) -> list[dict]: ...

    # --- Built-in helpers ---
    async def _retry(fn, *args, max_retries=4, base_delay=10, label="") -> Any: ...
    async def _generate_chained_subclips(db, job, scene, ...) -> tuple[str, float]: ...
    async def _generate_sub_scene_prompts(db, job, scene, num_clips) -> list[str]: ...
```

## Scene Lifecycle

Every job follows this state machine:

```
pending → planning → planned → generating_images → images_ready
→ generating_videos → videos_ready → rendering → completed
```

The `dispatch_stage()` function in `app/workers/dispatcher.py` maps each
stage transition to the corresponding plugin method.

## Retry Mechanism

All media generation calls are wrapped with `_retry()` which provides
exponential backoff (10s → 20s → 40s → 80s) for recoverable errors:

- Engine overloaded, capacity issues
- Rate limiting (429)
- Server errors (502, 503)
- Timeouts and connection failures
- Empty responses

Non-recoverable errors (invalid prompts, auth failures) propagate immediately.
After 4 retries, the scene is marked `failed` and the pipeline continues.

## Sub-Clip Chaining (Scenes > 5s)

Video models max out at ~5s per clip. For scenes longer than 5s, the
`generate_videos()` method automatically:

1. Splits the scene into N 5s sub-clips
2. Generates evolving prompts per sub-clip via LLM
3. Generates each sub-clip using I2V (image-to-video) with the previous
   clip's ~80% frame as the seed image
4. Merges sub-clips with 0.3s crossfade transitions

## Plugin Registration

Plugins are discovered at startup by scanning `backend/plugins/*/` for
packages with a `create_plugin()` function in `__init__.py`:

```python
# backend/plugins/my_plugin/__init__.py
from .plugin import MyPlugin

def create_plugin():
    return MyPlugin()
```

The registry (`app/plugins/registry.py`) provides:

- `discover_plugins()` — scan and register all plugins
- `get_plugin(plugin_id)` — retrieve by ID
- `get_plugin_for_template(config)` — match template config to plugin

## Frontend Integration

The generic `SceneEditor` (`frontend/src/pages/SceneEditor.tsx`) auto-detects
the plugin from the job's template config and renders the appropriate sidebar
panel from `frontend/src/pages/editor/`. Plugin-specific panels handle:

- Input collection (audio upload, script editor, prompt enhancer)
- Scene planning (trigger planning, edit scenes)
- Plugin-specific workflow options

## Auto-Avatar Creation

When a job is created without explicit avatar assignments (the `avatars` list
in `job.input_data` is empty or missing), the `enrich_inputs()` stage
auto-generates characters:

1. **LLM generates character descriptions**: The LLM analyzes the job prompt
   and creates 1-3 distinct characters, each with a name, gender, bio, and
   role within the video.
2. **Reference images are generated**: The image generation pipeline creates a
   portrait for each character (1:1 aspect ratio, photorealistic).
3. **Avatars are persisted**: `Avatar` and `AvatarImage` records are saved to
   the database, linked to the job's user.
4. **Context is populated**: The resolved avatar dicts (matching the same
   format as `_resolve_avatars()`) are written to
   `context["avatars"]` with `primary_image_path` set for each
   character.

If the LLM is unavailable or image generation fails, the method degrades
gracefully: missing images result in `primary_image_path=None` (text-only
characters), and complete failures leave `context["avatars"]` unset.

## Image-to-Image Pipeline

The `generate_images()` stage automatically uses avatar reference images for
img2img:

1. **Reference image resolution**: At the start of `generate_images()`, the
   first avatar's `primary_image_path` is resolved from
   `context["avatars"]`.
2. **img2img call**: Each scene's image is generated by passing
   `reference_image_path=<path>` and `reference_image_strength=0.75` to
   `generate_image()`. The provider receives these as `**kwargs` and uses
   them for image-guided generation.
3. **T2I fallback**: If the img2img call exhausts all retries, the pipeline
   retries automatically without the reference image (pure text-to-image).
   This ensures scenes still get images even if the reference image is
   incompatible with the provider's model.
4. **No-avatar fallback**: If no avatars are configured, or the primary image
   is missing from disk, `generate_images()` falls back to pure T2I for all
   scenes. No special handling is needed in the provider.

The same pattern applies to `generate_videos()` for I2V: scenes use
`scene.reference_image_path` (set by `generate_images()`) as the seed image
for video generation.

## Model Capabilities Context

The scene planner receives an auto-generated `MODEL CAPABILITIES` block in
its system prompt, built by `build_model_capabilities_context()` from
`app/services/model_capabilities.py`. This block tells the LLM what each
model can do:

- Which models accept text prompts, reference images, start/end frames
- Whether models output images or video
- Per-model constraints (max duration, aspect ratios)
- Scene planning instructions tailored to the model type

For example, if the video model supports I2V but not T2V, the planner
receives instructions to provide a seed image for each scene. If the image
model supports img2img, the planner is told that reference images will be
used for character consistency.

This context is generated once during `enrich_inputs()` and appended to the
planner prompt. It enables the LLM to produce scene descriptions that match
the actual capabilities of the configured models.

### Planning Constraints Context

In addition to model capabilities, every scene planner should also receive a
`PLANNING CONSTRAINTS` block built by
`build_scene_constraints_context()` from
`app/services/model_capabilities.py`. This block includes:

- Target total duration for the video
- The selected video model's max clip duration
- Supported aspect ratios for image/video models
- Max prompt length for image and text models

The planner must respect these limits: scene durations should not exceed the
video model's max clip duration (the pipeline will chain longer scenes into
sub-clips, but planning within the limit is more efficient), and image
prompts must be kept within the image model's `max_prompt_length`. Prompts
that exceed the limit are automatically truncated after planning.

## Creating a New Plugin

See [docs/WRITING_PLUGINS.md](WRITING_PLUGINS.md) for a step-by-step guide.
