# VidForge Plugin Architecture — Design Proposal

## Problem Statement

The current system hard-codes template-specific logic in shared files:

| Concern | Where it lives today |
|---|---|
| Scene planning (music video) | `services/music_video_planner.py` |
| Lyrics extraction | `services/lyrics_extractor.py` |
| Scene planning (prompt-to-video) | **Missing** — single-shot generation |
| Image generation workflow | `services/media_generator.py` (mixed Flux/Wan/LTX code) |
| Video generation workflow | `services/media_generator.py` + `services/video_generator.py` |
| Scene orchestration | `workers/tasks.py` (4 x 300-line stage functions) |
| Scene editor UI | `pages/MusicVideoEditor.tsx` (719 lines) |
| Scene API | `api/scenes.py` (716 lines) |

Every new template type (e.g., "AI commercial", "social media reel", "documentary") would require touching all these files. The scene-based workflow is tightly coupled to the music-video use case despite being applicable to *any* template that generates multiple clips.

## Core Insight

**Scene-based generation is the universal pattern.** Even "prompt-to-video" needs it — current video models max out at ~5 seconds per clip. A 30-second video from a text prompt is really "plan scenes → generate images → generate clips → stitch."

The system should treat every template as a scene-based pipeline with pluggable stages.

---

## Proposed Architecture

### 1. Three-Layer Model

```
┌─────────────────────────────────────────────────────┐
│  Core System                                        │
│  • Model registry (image, video, text, audio)       │
│  • Scene management (CRUD, re-render, ordering)     │
│  • Rendering pipeline (merge, audio mix, preview)   │
│  • Job lifecycle (queued → planning → rendering)    │
│  • Storage / media library                          │
├─────────────────────────────────────────────────────┤
│  Plugin Interface (contracts)                        │
│  • TemplateDefinition (YAML + metadata)             │
│  • PipelineHandler (per-stage async methods)        │
│  • UI Schema (form fields + editor panels)          │
├─────────────────────────────────────────────────────┤
│  Plugins (bundled or third-party)                   │
│  • prompt_to_video/                                 │
│  • music_video/                                     │
│  • script_to_video/                                 │
│  • (future: commercial/, reel/, documentary/…)      │
└─────────────────────────────────────────────────────┘
```

### 2. Plugin Structure

Each plugin is a Python package with a well-defined entry point:

```
backend/plugins/
├── prompt_to_video/
│   ├── __init__.py          # exports Plugin class
│   ├── plugin.py            # PromptToVideoPlugin(PluginBase)
│   ├── planner.py           # scene planning from a single prompt
│   ├── template.yaml        # template definition
│   └── ui_schema.json       # form fields + editor panels
├── music_video/
│   ├── __init__.py
│   ├── plugin.py            # MusicVideoPlugin(PluginBase)
│   ├── planner.py           # scene planning from lyrics
│   ├── lyrics.py            # audio → lyrics extraction
│   ├── audio_tools.py       # duration, beat detection
│   ├── template.yaml
│   └── ui_schema.json
└── script_to_video/
    ├── __init__.py
    ├── plugin.py
    ├── planner.py           # scene planning from script segments
    ├── tts.py               # narration generation
    ├── template.yaml
    └── ui_schema.json
```

### 3. Plugin Base Class

```python
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class PluginBase(ABC):
    """Contract every template plugin must implement."""

    # --- Identity -------------------------------------------------------

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier, e.g. 'music_video'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description."""

    # --- Template definition --------------------------------------------

    @abstractmethod
    def get_template_definition(self) -> dict:
        """Return the YAML-loaded template definition (inputs, pipeline)."""

    # --- Stage handlers -------------------------------------------------
    # The core calls these in sequence.  Each stage receives the DB session,
    # the job, and any stage-specific context.

    @abstractmethod
    async def plan_scenes(
        self, db, job, context: dict,
    ) -> dict:
        """Analyze inputs and create VideoScene rows.

        Returns context dict passed to subsequent stages.
        Must create VideoScene objects in the DB.

        Example return:
            {"scene_count": 12, "summary": "..."}
        """

    async def generate_images(
        self, db, job, scenes: list, context: dict,
    ) -> dict:
        """Generate seed/reference images for scenes.

        Default implementation: use core image generation with each
        scene's image_prompt.  Override for custom workflows.
        """

    async def generate_videos(
        self, db, job, scenes: list, context: dict,
    ) -> dict:
        """Generate video clips for scenes.

        Default implementation: use core video generation with each
        scene's reference image + visual description.
        """

    async def render(
        self, db, job, scenes: list, context: dict,
    ) -> dict:
        """Final rendering: merge clips, add audio, preview.

        Default implementation: core merge + audio mix.
        """

    # --- Optional: per-scene re-render hooks ----------------------------

    async def rerender_scene_image(
        self, db, job, scene, context: dict,
    ) -> str | None:
        """Re-generate a single scene's image. Returns relative path."""

    async def rerender_scene_video(
        self, db, job, scene, context: dict,
    ) -> str | None:
        """Re-generate a single scene's video. Returns relative path."""

    # --- Optional: input enrichment -------------------------------------

    async def enrich_inputs(
        self, db, job, context: dict,
    ) -> dict:
        """Pre-process raw inputs before scene planning.

        E.g., extract lyrics from audio, parse script annotations.
        Updates job.input_data with enriched fields.
        Returns updated context.
        """

    # --- UI metadata ---------------------------------------------------

    def get_ui_schema(self) -> dict:
        """Return JSON schema for the template's editor UI.

        Default: auto-generate from template definition inputs.
        """
        return {}

    def get_editor_panels(self) -> list[dict]:
        """Return list of editor panels for the scene editor.

        Each panel: {"id": str, "label": str, "component": str, "props": {}}

        Default: ["scenes", "timeline", "export"]
        """
        return [
            {"id": "scenes", "label": "Scenes", "component": "SceneGrid"},
            {"id": "timeline", "label": "Timeline", "component": "Timeline"},
            {"id": "export", "label": "Export", "component": "ExportPanel"},
        ]
```

### 4. Core Scene Lifecycle (Universal)

Every job follows the same state machine:

```
pending → planning → planned → generating_images → images_ready
→ generating_videos → videos_ready → rendering → completed
```

At each transition the core calls the plugin's corresponding method.

**Key feature**: individual scenes are independently re-renderable at any time.
The UI shows each scene's image and video as soon as they exist, and provides
a "Re-render" button that calls `plugin.rerender_scene_image()` or
`plugin.rerender_scene_video()` for just that scene.

### 5. Core Services (shared across all plugins)

```python
# Core provides these as injectable dependencies:

class ImageGenerator:
    """Shared image generation via ComfyUI."""
    async def generate(prompt, ..., provider_id) -> str: ...

class VideoGenerator:
    """Shared video generation via ComfyUI."""
    async def generate(prompt, ..., reference_image, provider_id) -> str: ...

class LLMService:
    """Shared LLM access via Ollama."""
    async def generate(system, prompt, ...) -> str: ...

class AudioService:
    """Shared audio tools."""
    async def get_duration(path) -> float: ...
    async def extract_lyrics(path) -> dict: ...
    async def generate_tts(text, voice) -> str: ...

class Renderer:
    """Shared video rendering tools."""
    async def merge(clips) -> str: ...
    async def add_audio(video, audio, volume) -> str: ...
    async def generate_preview(video) -> str: ...
```

### 6. Plugin Registration

```python
# In the plugin package's __init__.py:
from .plugin import MusicVideoPlugin

def create_plugin():
    return MusicVideoPlugin()

# Discovery: core scans backend/plugins/*/  for create_plugin()
```

The core loads all plugins at startup and registers their template
definitions in the DB (marked `is_builtin=True` for bundled plugins).

### 7. Frontend: Dynamic Template UI

Instead of a hardcoded `MusicVideoEditor.tsx`, the frontend uses a
generic `SceneEditor` component that:

1. Fetches the template's `ui_schema` and `editor_panels` from the API
2. Renders the appropriate input form based on `template.inputs`
3. Shows a universal scene grid with per-scene thumbnails, re-render buttons
4. Shows a timeline view
5. Shows an export panel with template-specific options

Template-specific React components can be loaded dynamically:

```
frontend/src/plugins/
├── music_video/
│   ├── LyricsPanel.tsx      # shows/edit extracted lyrics
│   └── AudioUpload.tsx      # audio upload with duration display
├── prompt_to_video/
│   └── PromptEnhancer.tsx   # prompt editing with enhancement preview
└── script_to_video/
    ├── ScriptEditor.tsx     # script editor with annotation highlighting
    └── VoiceSelector.tsx    # TTS voice selection with preview
```

### 8. Prompt-to-Video Goes Scene-Based

Currently "Prompt to Video" generates a single clip. The refactored
`prompt_to_video` plugin would:

1. **plan_scenes**: Send the prompt to the LLM with instructions to
   break it into 3-6 second visual segments
2. **generate_images**: Create a seed image per scene
3. **generate_videos**: Create a clip per scene
4. **render**: Stitch clips together

This matches what the hardware can actually do (Wan2.2 generates ~5s clips)
and gives users the same granular control they have with music videos.

### 9. Migration Path

| Phase | What | Risk |
|---|---|---|
| **Phase 1** | Create `PluginBase` ABC, `plugins/` directory, registration | Low — additive |
| **Phase 2** | Extract `music_video` plugin from current code | Medium — move code |
| **Phase 3** | Extract `prompt_to_video` plugin, add scene planning | Medium — new feature |
| **Phase 4** | Extract `script_to_video` plugin | Medium — new feature |
| **Phase 5** | Generic `SceneEditor` frontend component | Medium — UI refactor |
| **Phase 6** | Remove hardcoded template logic from `tasks.py` | Low — deletion |

### 10. File Impact Summary

**New files:**
```
backend/app/plugins/__init__.py
backend/app/plugins/base.py                    # PluginBase ABC
backend/app/plugins/registry.py               # discovery & registration
backend/app/plugins/prompt_to_video/           # full plugin package
backend/app/plugins/music_video/               # full plugin package
backend/app/plugins/script_to_video/           # full plugin package
backend/app/services/core/                     # shared services refactored
frontend/src/plugins/                          # plugin UI components
frontend/src/components/SceneEditor/           # generic scene editor
```

**Modified files:**
```
backend/app/workers/tasks.py                   # slim dispatcher → plugin calls
backend/app/api/scenes.py                      # use plugin for per-scene ops
backend/app/api/jobs.py                        # generic template dispatch
backend/app/main.py                            # plugin registration on startup
frontend/src/pages/JobDetail.tsx               # use generic SceneEditor
frontend/src/pages/MusicVideoEditor.tsx        # replaced by generic editor
```

**Deleted (absorbed into plugins):**
```
backend/app/services/music_video_planner.py    # → plugins/music_video/planner.py
backend/app/services/lyrics_extractor.py        # → plugins/music_video/lyrics.py
backend/app/services/script_parser.py           # → plugins/script_to_video/parser.py
```

---

## Open Questions

1. **Plugin configuration**: Should plugins be able to define their own DB tables
   (e.g., `poe_models` is specific to the Poe provider — should it be a plugin)?
   → *Recommendation: No. Keep provider/model management in core.*

2. **Third-party plugins**: Should we support external plugin installation
   (pip install / drag-drop folder) or only bundled?
   → *Recommendation: Start bundled-only, design for external later.*

3. **Custom scene fields**: Different templates need different per-scene data
   (music video has `lyrics_segment`, prompt-to-video doesn't).
   → *Recommendation: Use a JSONB `metadata` column on VideoScene that plugins
   can read/write freely.*

4. **Rendering options**: Templates have different export options
   (music video: audio volume; script: voice selection).
   → *Recommendation: Plugin returns export option schema from `get_ui_schema()`.*
