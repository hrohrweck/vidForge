"""
Prompt to Video plugin.

Breaks a single text prompt into N visual segments (each ~5 s),
generates seed images and video clips per segment, then stitches
them together.  This matches what the GPU can actually do — Wan2.2
produces ~5 s per clip.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, VideoScene
from app.plugins.base import PluginBase

logger = logging.getLogger(__name__)


class PromptToVideoPlugin(PluginBase):
    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def plugin_id(self) -> str:
        return "prompt_to_video"

    @property
    def display_name(self) -> str:
        return "Prompt to Video"

    @property
    def description(self) -> str:
        return "Generate a video from a text prompt using scene-based generation"

    # ------------------------------------------------------------------
    # Template definition
    # ------------------------------------------------------------------

    def get_template_definition(self) -> dict[str, Any]:
        import yaml

        yaml_path = Path(__file__).parent / "template.yaml"
        template = yaml.safe_load(yaml_path.read_text())
        # Mark as scene-based so the core uses the scene lifecycle
        template.setdefault("config", {})["workflow_type"] = "scene_based"
        return template

    def get_input_schema(self) -> type[Any] | None:
        from .schemas import PromptToVideoInput

        return PromptToVideoInput

    # ------------------------------------------------------------------
    # Stage: enrich inputs
    # ------------------------------------------------------------------

    async def enrich_inputs(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        input_data = job.input_data or {}
        style = input_data.get("style", "realistic")
        text_model = input_data.get("text_model")

        provider = None
        if text_model:
            from app.services.llm_service import resolve_llm

            provider = await resolve_llm(text_model, db)

        # Optionally enhance the prompt via LLM
        prompt = input_data.get("prompt", "")
        enhance = input_data.get("enhance_prompt", True)
        if enhance and prompt:
            from app.services.llm_service import PromptEnhancer

            enhancer = PromptEnhancer(provider=provider, model=text_model)
            try:
                enhanced = await enhancer.enhance(prompt, style)
                job.input_data = {**input_data, "enhanced_prompt": enhanced}
            finally:
                await enhancer.close()
        elif provider is not None and hasattr(provider, "shutdown"):
            await provider.shutdown()

        return context

    async def render(
        self,
        db: AsyncSession,
        job: Job,
        scenes: list[VideoScene],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        input_data = job.input_data or {}
        if input_data.get("generate_audio"):
            try:
                from app.config import get_settings
                from app.services.audio_generation import MusicGenService

                svc = MusicGenService()
                if await svc.is_available():
                    settings = get_settings()
                    output_dir = Path(settings.storage_path) / "output" / str(job.id)
                    output_dir.mkdir(parents=True, exist_ok=True)
                    audio_path = str(output_dir / "background_music.mp3")
                    prompt = input_data.get("audio_prompt") or input_data.get("prompt", "")
                    duration = min(float(input_data.get("duration", 30)), 120)

                    logger.info("Generating prompt-to-video background music: %s", prompt)
                    actual_path = await svc.generate(
                        prompt=prompt,
                        output_path=audio_path,
                        duration=duration,
                        output_format="mp3",
                    )
                    context["background_music"] = actual_path
                    context["background_music_volume"] = input_data.get("audio_volume", 0.3)
                else:
                    logger.warning("AudioCraft server not available, skipping generated audio")
            except Exception:
                logger.warning("Failed to generate prompt-to-video audio", exc_info=True)

        return await super().render(db, job, scenes, context)

    # ------------------------------------------------------------------
    # Stage: plan scenes
    # ------------------------------------------------------------------

    async def plan_scenes(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        from app.api.models import get_model
        from app.services.avatar_prompt_builder import (
            build_avatar_context_string,
            build_combined_context,
        )
        from app.services.llm_service import resolve_llm
        from app.services.model_capabilities import (
            build_model_capabilities_context,
            build_reference_capacity_context,
            build_scene_constraints_context,
        )
        from app.services.model_metadata import get_model_constraint

        from .planner import plan_scenes_from_prompt

        input_data = job.input_data or {}
        original_prompt = input_data.get("prompt", "")
        prompt = input_data.get("enhanced_prompt") or original_prompt
        style = input_data.get("style", "realistic")
        duration = input_data.get("duration", 30)
        text_model = input_data.get("text_model")
        video_model = input_data.get("video_model")
        image_model = input_data.get("image_model")

        provider = None
        if text_model:
            provider = await resolve_llm(text_model, db)

        avatars = context.get("avatars", [])
        objects = context.get("objects", [])
        avatars_context = build_avatar_context_string(avatars)

        video_config = None
        if video_model:
            video_config = await get_model(db, video_model)
        image_config = None
        if image_model:
            image_config = await get_model(db, image_model)
        text_config = None
        if text_model:
            text_config = await get_model(db, text_model)
        model_capabilities_context = build_model_capabilities_context(
            video_model_config=video_config,
            image_model_config=image_config,
        )
        constraints_context = build_scene_constraints_context(
            video_model_config=video_config,
            image_model_config=image_config,
            text_model_config=text_config,
            target_duration=duration,
        )
        max_clip_duration = 5.0
        if video_config:
            max_clip_duration = get_model_constraint(video_config, "max_duration", 5)
        image_max_prompt_length = None
        if image_config:
            image_max_prompt_length = get_model_constraint(image_config, "max_prompt_length")

        objects_context = build_combined_context(avatars, objects) or None
        reference_capacity_context = build_reference_capacity_context(
            video_model_config=video_config,
            char_count=len(avatars),
        )

        result = await plan_scenes_from_prompt(
            prompt=prompt,
            duration=duration,
            style=style,
            avatars_context=avatars_context or None,
            model_capabilities_context=model_capabilities_context,
            constraints_context=constraints_context,
            objects_context=objects_context,
            reference_capacity_context=reference_capacity_context,
            provider=provider,
            model=text_model,
            max_clip_duration=max_clip_duration,
            image_max_prompt_length=image_max_prompt_length,
            original_prompt=original_prompt,
        )

        scenes = result["scenes"]
        context["object_selections"] = result.get("object_selections", [])

        # Clear any existing scenes
        await db.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
        await db.commit()

        for i, scene_data in enumerate(scenes):
            scene = VideoScene(
                job_id=job.id,
                scene_number=i + 1,
                start_time=scene_data["start_time"],
                end_time=scene_data["end_time"],
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
    # generate_images / generate_videos / render: use defaults
    # ------------------------------------------------------------------

    # (inherited from PluginBase — they iterate scenes and call core services)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def get_ui_schema(self) -> dict[str, Any]:
        return {
            "editor_panels": [
                {"id": "scenes", "label": "Scenes", "component": "SceneGrid"},
                {"id": "timeline", "label": "Timeline", "component": "Timeline"},
                {"id": "export", "label": "Export", "component": "ExportPanel"},
            ],
        }
