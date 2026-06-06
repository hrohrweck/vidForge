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

    # ------------------------------------------------------------------
    # Stage: enrich inputs
    # ------------------------------------------------------------------

    async def enrich_inputs(
        self, db: AsyncSession, job: Job, context: dict[str, Any],
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
            enhancer = PromptEnhancer(provider=provider)
            try:
                enhanced = await enhancer.enhance(prompt, style)
                job.input_data = {**input_data, "enhanced_prompt": enhanced}
            finally:
                await enhancer.close()
        elif provider is not None and hasattr(provider, "shutdown"):
            await provider.shutdown()

        return context

    # ------------------------------------------------------------------
    # Stage: plan scenes
    # ------------------------------------------------------------------

    async def plan_scenes(
        self, db: AsyncSession, job: Job, context: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.avatar_prompt_builder import build_avatar_context_string
        from app.services.llm_service import resolve_llm

        from .planner import plan_scenes_from_prompt

        input_data = job.input_data or {}
        prompt = input_data.get("enhanced_prompt") or input_data.get("prompt", "")
        style = input_data.get("style", "realistic")
        duration = input_data.get("duration", 10)
        text_model = input_data.get("text_model")

        provider = None
        if text_model:
            provider = await resolve_llm(text_model, db)

        avatars_context = build_avatar_context_string(context.get("avatars", []))

        scenes = await plan_scenes_from_prompt(
            prompt=prompt,
            duration=duration,
            style=style,
            avatars_context=avatars_context or None,
            provider=provider,
        )

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
