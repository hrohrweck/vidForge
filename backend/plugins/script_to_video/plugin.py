"""
Script to Video plugin.

Parses a script with bracket annotations (e.g. ``[Show a sunset]``),
generates narration via TTS, plans scenes from visual cues, generates
images and videos per scene, then composites everything.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import Job, VideoScene
from app.plugins.base import PluginBase

logger = logging.getLogger(__name__)


class ScriptToVideoPlugin(PluginBase):

    @property
    def plugin_id(self) -> str:
        return "script_to_video"

    @property
    def display_name(self) -> str:
        return "Script to Video"

    @property
    def description(self) -> str:
        return "Generate a video from a script with annotation-based visual directions and optional narration"

    def get_template_definition(self) -> dict[str, Any]:
        import yaml

        yaml_path = Path(__file__).parent / "template.yaml"
        template = yaml.safe_load(yaml_path.read_text())
        template.setdefault("config", {})["workflow_type"] = "scene_based"
        return template

    # ------------------------------------------------------------------
    # enrich_inputs: parse script, generate narration
    # ------------------------------------------------------------------

    async def enrich_inputs(
        self, db: AsyncSession, job: Job, context: dict[str, Any],
    ) -> dict[str, Any]:
        from .script_parser import parse_script

        input_data = job.input_data or {}
        script = input_data.get("script", "")
        if not script:
            raise RuntimeError("No script provided")

        # Parse script into segments
        segments = parse_script(script)
        context["segments"] = segments

        # Estimate total duration (avg 2.5 words/sec narration speed)
        total_words = sum(len(s["narration"].split()) for s in segments)
        estimated_duration = total_words / 2.5
        context["total_duration"] = estimated_duration

        # Optionally generate TTS
        voice = input_data.get("voice", "default")
        if voice and voice != "none":
            from .tts import generate_narration
            narration_path, timings = await generate_narration(
                segments=[s["narration"] for s in segments],
                voice=voice,
                output_dir=Path(get_settings().storage_path) / "output" / str(job.id),
            )
            job.input_data = {
                **input_data,
                "narration_path": narration_path,
                "timings": timings,
            }
            context["narration_path"] = narration_path
            context["timings"] = timings

            # Recalculate duration from actual timings
            if timings:
                context["total_duration"] = timings[-1].get("end", estimated_duration)

        return context

    # ------------------------------------------------------------------
    # plan_scenes: create scenes from parsed segments
    # ------------------------------------------------------------------

    async def plan_scenes(
        self, db: AsyncSession, job: Job, context: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.avatar_prompt_builder import build_avatar_context_string
        from app.services.llm_service import resolve_llm

        from .planner import plan_scenes_from_script

        input_data = job.input_data or {}
        segments = context.get("segments", [])
        style = input_data.get("style", "realistic")
        duration = context.get("total_duration", 30)
        text_model = input_data.get("text_model")

        provider = None
        if text_model:
            provider = await resolve_llm(text_model, db)

        avatars_context = build_avatar_context_string(context.get("avatars", []))

        scenes = await plan_scenes_from_script(
            segments=segments,
            duration=duration,
            style=style,
            avatars_context=avatars_context or None,
            provider=provider,
            model=text_model,
        )

        await db.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
        await db.commit()

        for i, scene_data in enumerate(scenes):
            scene = VideoScene(
                job_id=job.id,
                scene_number=i + 1,
                start_time=scene_data["start_time"],
                end_time=scene_data["end_time"],
                lyrics_segment=scene_data.get("narration"),
                visual_description=scene_data["visual_description"],
                image_prompt=scene_data["image_prompt"],
                mood=scene_data.get("mood", "neutral"),
                camera_movement=scene_data.get("camera_movement", "static"),
                status="pending",
            )
            db.add(scene)

        job.stage = "planned"
        job.workflow_type = "scene_based"
        await db.commit()

        return {"scene_count": len(scenes)}

    # ------------------------------------------------------------------
    # render: add narration + optional background music
    # ------------------------------------------------------------------

    async def render(
        self, db: AsyncSession, job: Job,
        scenes: list[VideoScene], context: dict[str, Any],
    ) -> dict[str, Any]:
        # Pass narration audio to the renderer
        narration_path = context.get("narration_path")
        if narration_path:
            context["audio_file"] = narration_path
            context["audio_volume"] = 1.0

        # Generate background music if requested
        input_data = job.input_data or {}
        if input_data.get("background_music", True):
            try:
                from app.services.audio_generation import MusicGenService

                svc = MusicGenService()
                if await svc.is_available():
                    # Build a music prompt from the script content
                    script_text = input_data.get("script", "")
                    music_prompt = _build_music_prompt(script_text)
                    total_duration = context.get("total_duration", 30)

                    settings = get_settings()
                    output_dir = Path(settings.storage_path) / "output" / str(job.id)
                    output_dir.mkdir(parents=True, exist_ok=True)
                    bgm_path = str(output_dir / "background_music.mp3")

                    logger.info("Generating background music (%.0fs): %s", total_duration, music_prompt)
                    actual_path = await svc.generate(
                        prompt=music_prompt,
                        output_path=bgm_path,
                        duration=min(total_duration, 120),
                        output_format="mp3",
                    )
                    context["background_music"] = actual_path
                    context["background_music_volume"] = 0.3
                    logger.info("Background music generated: %s", actual_path)
                else:
                    logger.warning("AudioCraft server not available, skipping background music")
            except Exception:
                logger.warning("Failed to generate background music", exc_info=True)

        return await super().render(db, job, scenes, context)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def get_ui_schema(self) -> dict[str, Any]:
        return {
            "editor_panels": [
                {"id": "script", "label": "Script", "component": "ScriptEditor"},
                {"id": "scenes", "label": "Scenes", "component": "SceneGrid"},
                {"id": "timeline", "label": "Timeline", "component": "Timeline"},
                {"id": "export", "label": "Export", "component": "ExportPanel"},
            ],
        }


def _build_music_prompt(script_text: str) -> str:
    """Derive a music generation prompt from the script content."""
    # Take first 200 chars of the script as inspiration
    snippet = script_text[:200].replace("\n", " ").strip()
    # Remove bracket annotations
    import re
    snippet = re.sub(r"\[[^\]]+\]", "", snippet).strip()
    if len(snippet) > 100:
        snippet = snippet[:100]
    return f"Subtle ambient background music for a video. Mood: {snippet}"
