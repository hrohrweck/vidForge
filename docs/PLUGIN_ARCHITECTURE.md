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
│  • Media generation (ComfyUI, Poe providers)        │
│  • Video rendering (FFmpeg merge, audio mix)        │
│  • Job lifecycle (dispatcher → plugin stages)       │
│  • Storage backends (local, S3, SSH)                │
├─────────────────────────────────────────────────────┤
│  Plugin Interface (PluginBase ABC)                   │
│  • enrich_inputs()   — pre-process raw inputs       │
│  • plan_scenes()     — create VideoScene rows        │
│  • generate_images() — seed images per scene         │
│  • generate_videos() — video clips per scene         │
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

## Creating a New Plugin

See [docs/WRITING_PLUGINS.md](WRITING_PLUGINS.md) for a step-by-step guide.
