"""
Music Video (Scene-Based) plugin.

Pipeline:
  1. enrich_inputs — extract lyrics from audio via Whisper
  2. plan_scenes   — call LLM to create scene plan from lyrics + style
  3. generate_images  — delegate to core (default impl)
  4. generate_videos  — delegate to core (default impl)
  5. render           — merge clips + add original audio (default impl)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, VideoScene
from app.plugins.base import PluginBase

logger = logging.getLogger(__name__)


class MusicVideoPlugin(PluginBase):

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def plugin_id(self) -> str:
        return "music_video"

    @property
    def display_name(self) -> str:
        return "Music Video (Scene-Based)"

    @property
    def description(self) -> str:
        return "Create a music video with multi-scene planning, seed image generation, and per-scene video generation"

    # ------------------------------------------------------------------
    # Template definition
    # ------------------------------------------------------------------

    def get_template_definition(self) -> dict[str, Any]:
        import yaml

        yaml_path = Path(__file__).parent / "template.yaml"
        return yaml.safe_load(yaml_path.read_text())

    # ------------------------------------------------------------------
    # Stage: enrich inputs
    # ------------------------------------------------------------------

    async def enrich_inputs(
        self, db: AsyncSession, job: Job, context: dict[str, Any],
    ) -> dict[str, Any]:
        from app.config import get_settings
        settings = get_settings()
        input_data = job.input_data or {}
        audio_file = input_data.get("audio_file")

        if not audio_file:
            raise RuntimeError("No audio_file provided for music video job")

        audio_path = Path(settings.storage_path).resolve() / audio_file
        if not audio_path.exists():
            raise RuntimeError(f"Audio file not found: {audio_path}")

        # Get duration
        from .audio_tools import get_audio_duration
        duration = await get_audio_duration(str(audio_path))
        context["audio_duration"] = duration

        # Extract lyrics
        if not input_data.get("lyrics"):
            from .lyrics import extract_lyrics
            lyrics = await extract_lyrics(str(audio_path))
            job.input_data = {**input_data, "lyrics": lyrics}

        # Store audio path for render stage
        context["audio_file"] = audio_file
        context["audio_volume"] = 1.0
        return context

    # ------------------------------------------------------------------
    # Stage: plan scenes
    # ------------------------------------------------------------------

    async def plan_scenes(
        self, db: AsyncSession, job: Job, context: dict[str, Any],
    ) -> dict[str, Any]:
        input_data = job.input_data or {}
        lyrics = input_data.get("lyrics", {})
        duration = context.get("audio_duration") or lyrics.get("duration", 30)
        style = input_data.get("style", "realistic")
        text_model = input_data.get("text_model")

        from app.services.llm_service import resolve_llm

        provider = None
        if text_model:
            provider = await resolve_llm(text_model, db)

        from .planner import plan_music_video
        plan = await plan_music_video(lyrics=lyrics, duration=duration, style=style, provider=provider, model=text_model)

        # Create VideoScene rows
        from sqlalchemy import delete as sa_delete

        await db.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
        await db.commit()

        for scene_data in plan.get("scenes", []):
            scene = VideoScene(
                job_id=job.id,
                scene_number=scene_data["scene_number"],
                start_time=scene_data["start_time"],
                end_time=scene_data["end_time"],
                lyrics_segment=scene_data.get("lyrics_segment"),
                visual_description=scene_data.get("visual_description"),
                image_prompt=scene_data.get("image_prompt"),
                mood=scene_data.get("mood", "neutral"),
                camera_movement=scene_data.get("camera_movement", "static"),
                status="pending",
            )
            db.add(scene)

        job.stage = "planned"
        job.workflow_type = "scene_based"
        await db.commit()

        return {
            "scene_count": len(plan.get("scenes", [])),
            "summary": plan.get("summary", ""),
        }

    # ------------------------------------------------------------------
    # UI metadata
    # ------------------------------------------------------------------

    def get_ui_schema(self) -> dict[str, Any]:
        return {
            "editor_panels": [
                {"id": "lyrics", "label": "Lyrics", "component": "LyricsPanel"},
                {"id": "scenes", "label": "Scenes", "component": "SceneGrid"},
                {"id": "timeline", "label": "Timeline", "component": "Timeline"},
                {"id": "export", "label": "Export", "component": "ExportPanel"},
            ],
        }

    def get_export_options_schema(self) -> dict[str, Any]:
        return {
            "properties": {
                "audio_volume": {
                    "type": "number",
                    "default": 1.0,
                    "minimum": 0,
                    "maximum": 2.0,
                    "title": "Audio Volume",
                },
                "background_music": {
                    "type": "string",
                    "title": "Background Music (optional file path)",
                },
                "background_music_volume": {
                    "type": "number",
                    "default": 0.3,
                    "minimum": 0,
                    "maximum": 1.0,
                    "title": "Background Music Volume",
                },
                "transition_type": {
                    "type": "string",
                    "enum": ["cut", "crossfade", "dissolve"],
                    "default": "cut",
                    "title": "Transition Type",
                },
            },
        }
