# Writing Plugins

This guide walks through creating a new template plugin for VidForge.
A plugin is a self-contained Python package that defines a template type —
its inputs, scene planning logic, and any custom pipeline behavior.

## Quick Start

### 1. Create the Plugin Package

```
backend/plugins/my_template/
├── __init__.py      # exports create_plugin()
├── plugin.py        # MyTemplatePlugin class
└── planner.py       # Scene planning logic
```

### 2. `__init__.py`

```python
from .plugin import MyTemplatePlugin

def create_plugin():
    return MyTemplatePlugin()
```

### 3. `plugin.py`

```python
from typing import Any
from uuid import UUID

from app.plugins.base import PluginBase


class MyTemplatePlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "my_template"

    @property
    def display_name(self) -> str:
        return "My Template"

    @property
    def description(self) -> str:
        return "Description shown in the UI."

    def get_template_definition(self) -> dict:
        return {
            "name": "My Template",
            "description": self.description,
            "workflow_type": "scene_based",
            "inputs": [
                {
                    "name": "prompt",
                    "type": "text",
                    "required": True,
                    "description": "Describe your video",
                },
                {
                    "name": "style",
                    "type": "select",
                    "required": False,
                    "default": "realistic",
                    "options": ["realistic", "anime", "cinematic"],
                },
            ],
            "outputs": ["video"],
            "config": {
                "plugin_id": self.plugin_id,
            },
        }

    async def enrich_inputs(self, db, job, context):
        """Optional: pre-process inputs before planning."""
        # Example: validate prompt, generate metadata
        return context

    async def plan_scenes(self, db, job, context):
        """Required: create VideoScene rows in the database."""
        from app.database import VideoScene
        from .planner import plan_my_scenes

        input_data = job.input_data or {}
        style = input_data.get("style", "realistic")
        prompt = input_data.get("prompt", "")
        duration = input_data.get("duration", 30)

        scenes = await plan_my_scenes(prompt, duration, style)

        for s in scenes:
            scene = VideoScene(
                job_id=job.id,
                scene_number=s["scene_number"],
                start_time=s["start_time"],
                end_time=s["end_time"],
                visual_description=s.get("visual_description", ""),
                image_prompt=s.get("image_prompt", ""),
                mood=s.get("mood", "neutral"),
                camera_movement=s.get("camera_movement", "static"),
                status="pending",
            )
            db.add(scene)

        await db.flush()
        return {"scene_count": len(scenes)}
```

### 4. `planner.py`

```python
from app.services.llm_service import LLMService

SYSTEM_PROMPT = """You are a video director. Break the user's prompt into
a series of visual scenes for AI video generation.

Each scene should be 3-15 seconds long. Output ONLY valid JSON:
{"scenes": [{"start_time": 0.0, "end_time": 5.0, "visual_description":
"description", "image_prompt": "detailed image prompt", "mood": "mood",
"camera_movement": "movement"}]}

Guidelines:
- Scene duration: 3-15 seconds each
- Image prompts: 10-25 words, highly visual, specific
- CRITICAL: Every image_prompt MUST begin with the requested visual style.
- Ensure smooth narrative flow between scenes
- Total duration should match the requested duration"""


async def plan_my_scenes(
    prompt: str,
    duration: float,
    style: str,
) -> list[dict]:
    llm = LLMService()
    try:
        response = await llm.generate(
            f"Create a scene plan for a {duration}-second video.\n"
            f"Style: {style}\nPrompt: {prompt}",
            system=SYSTEM_PROMPT,
        )
        import json
        parsed = json.loads(response)
        return parsed.get("scenes", _fallback(prompt, duration))
    except Exception:
        return _fallback(prompt, duration)


def _fallback(prompt: str, duration: float) -> list[dict]:
    n = max(1, int(duration / 5))
    d = duration / n
    return [
        {
            "scene_number": i + 1,
            "start_time": round(i * d, 2),
            "end_time": round((i + 1) * d, 2),
            "visual_description": f"Scene {i+1}: {prompt}",
            "image_prompt": f"Visual scene {i+1}: {prompt}",
            "mood": "neutral",
            "camera_movement": "static",
        }
        for i in range(n)
    ]
```

### 5. Add a Frontend Panel (Optional)

If your plugin needs custom UI in the scene editor, create a panel:

```tsx
// frontend/src/pages/editor/MyTemplatePanel.tsx
interface Props {
  job: any
  jobId: string
  scenes: any[]
  planningMode?: boolean
}

export function MyTemplatePanel({ job, jobId, scenes, planningMode }: Props) {
  if (planningMode) {
    return <div>Configure your video...</div>
  }
  return <div>Plugin-specific info...</div>
}
```

Then add it to `SceneEditor.tsx` alongside the existing panels.

## What You Get for Free

The `PluginBase` class provides sensible defaults for most pipeline stages:

| Stage | Default Behavior |
|---|---|
| `generate_images()` | Calls `generate_image()` for each scene's `image_prompt` |
| `generate_videos()` | Single clip for scenes ≤5s, sub-clip chain for longer scenes |
| `render()` | Merges clips, adds audio, generates preview |
| `rerender_scene_image()` | Re-generates a single scene's seed image |
| `rerender_scene_video()` | Re-generates a single scene's video clip |

Override any of these if your template needs different behavior.

## Retry Behavior

All `generate_image` and `generate_video` calls are automatically retried
up to 4 times with exponential backoff (10s → 20s → 40s → 80s) on
recoverable errors (overloaded, timeout, rate limit, empty response).
Non-recoverable errors fail immediately.

## Scene Planning Guidelines

- **Scene duration**: 3–15 seconds per scene. Longer scenes are split
  into 5s sub-clips automatically.
- **image_prompt**: Should begin with the style qualifier. Keep under 25 words.
- **visual_description**: Longer description of what happens in the scene.
- **mood**: One of: neutral, happy, sad, energetic, calm, dramatic, mysterious
- **camera_movement**: One of: static, pan_left, pan_right, zoom_in, zoom_out,
  tilt_up, orbit

## Template Definition Schema

The dict returned by `get_template_definition()` follows this structure:

```python
{
    "name": str,                    # Display name
    "description": str,             # One-line description
    "workflow_type": "scene_based", # Must be "scene_based"
    "inputs": [                     # List of input definitions
        {
            "name": str,            # Input field name (used as key in input_data)
            "type": "text|number|select|boolean|file",
            "required": bool,
            "default": Any,         # Optional default value
            "description": str,     # Help text
            "options": list[str],   # For select type
        }
    ],
    "outputs": ["video"],
    "config": {
        "plugin_id": str,           # Must match plugin_id property
    }
}
```

## Testing Your Plugin

1. Start the backend — the plugin is auto-discovered at startup
2. Create a job via the API or UI using your template
3. Trigger scene planning — verify VideoScene rows are created
4. Generate images and videos — check the output files
5. Export the final video — verify it plays correctly

## Examples

The best reference is the existing plugins:

| Plugin | Key Feature |
|---|---|
| `prompt_to_video` | Simplest — just a prompt input + LLM scene planning |
| `script_to_video` | Script annotation parsing, TTS narration, background music |
| `music_video` | Audio upload, Whisper lyrics extraction, beat-synced scenes |

Start from `prompt_to_video` (simplest) and add complexity as needed.


## Plugin Base Internals

Plugin authors should continue importing only `PluginBase` from `app.plugins.base`.
The default stage implementations are split internally across `app.plugins.enrichment`
and `app.plugins.media_stages`, but those modules are implementation details and do
not change the public plugin contract. Override methods on `PluginBase` subclasses as
shown below rather than importing the mixins directly.
