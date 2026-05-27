"""
Base class that every template plugin must implement.

The core scene lifecycle is:

    pending → planning → planned → generating_images → images_ready
    → generating_videos → videos_ready → rendering → completed

At each transition the core calls the corresponding method on the
plugin that owns the job's template.  Plugins can override any stage;
sensible defaults are provided for the common case (generate per-scene
images then per-scene videos then merge).
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import Job, VideoScene


class PluginBase(ABC):
    """Contract every template plugin must implement."""

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier, e.g. ``'music_video'``."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description."""

    # ------------------------------------------------------------------
    # Template definition
    # ------------------------------------------------------------------

    @abstractmethod
    def get_template_definition(self) -> dict[str, Any]:
        """Return the template definition (inputs, pipeline, stages …).

        The dict has the same shape as a ``templates/*.yaml`` file.
        """

    # ------------------------------------------------------------------
    # Stage: enrich inputs (optional)
    # ------------------------------------------------------------------

    async def enrich_inputs(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Pre-process raw inputs before scene planning.

        E.g. extract lyrics from audio, parse script annotations.
        Update ``job.input_data`` with enriched fields.
        Return an updated *context* dict that is forwarded to
        :meth:`plan_scenes`.
        """
        return context

    # ------------------------------------------------------------------
    # Stage: plan scenes
    # ------------------------------------------------------------------

    @abstractmethod
    async def plan_scenes(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyse inputs and create :class:`VideoScene` rows.

        Must create :class:`VideoScene` objects in the DB.
        Returns a context dict forwarded to subsequent stages.

        Example return::

            {"scene_count": 12, "summary": "..."}
        """

    # ------------------------------------------------------------------
    # Stage: generate images
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    # Error substrings that indicate a transient / recoverable problem.
    _RECOVERABLE_MARKERS: tuple[str, ...] = (
        "overloaded",
        "rate limit",
        "rate_limit",
        "too many requests",
        "429",
        "503",
        "502",
        "timeout",
        "timed out",
        "connection",
        "connectionerror",
        "connection refused",
        "temporary",
        "retry",
        "capacity",
        "queue is full",
        "server error",
        "internal server error",
        "no output data",
        "returned no data",
        "returned no image",
        "returned no video",
    )

    @staticmethod
    def _is_recoverable(exc: Exception) -> bool:
        """Return True if *exc* looks like a transient error worth retrying."""
        msg = str(exc).lower()
        return any(marker in msg for marker in PluginBase._RECOVERABLE_MARKERS)

    @staticmethod
    async def _retry(
        fn,
        *args,
        max_retries: int = 4,
        base_delay: float = 10.0,
        label: str = "operation",
        **kwargs,
    ):
        """Call ``await fn(*args, **kwargs)`` with exponential backoff.

        Retries up to *max_retries* times on recoverable errors.
        Non-recoverable errors propagate immediately.
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if not PluginBase._is_recoverable(exc):
                    raise
                if attempt >= max_retries:
                    raise
                delay = base_delay * (2 ** attempt)  # 10s, 20s, 40s, 80s
                logger.warning(
                    "[%s] Attempt %d/%d failed (recoverable): %s — "
                    "retrying in %.0fs",
                    label, attempt + 1, max_retries + 1, exc, delay,
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------
    # Stage: generate images
    # ------------------------------------------------------------------

    async def generate_images(
        self,
        db: AsyncSession,
        job: Job,
        scenes: list[VideoScene],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate seed / reference images for each scene.

        The default implementation iterates over *scenes* and calls the
        core image generator for each scene's ``image_prompt``.
        """
        from app.services.media_generator import generate_image

        input_data = job.input_data or {}
        image_model = input_data.get("image_model")
        for scene in scenes:
            if scene.reference_image_path:
                continue
            prompt = scene.image_prompt or scene.visual_description or ""
            if not prompt:
                continue
            try:
                image_path, _media_id, _provider_id = await self._retry(
                    generate_image,
                    db=db,
                    job=job,
                    prompt=prompt,
                    scene_number=scene.scene_number,
                    model_preference=image_model,
                    provider_id=job.image_provider_id,
                    label=f"image-s{scene.scene_number}",
                )
                scene.reference_image_path = image_path
                scene.status = "image_ready"
                # Auto-import to media library
                await _import_scene_asset(
                    db, job, scene.reference_image_path,
                    f"scene-{scene.scene_number}-image",
                    "image", scene.scene_number,
                )
                # Update progress: 20% → 40% spread across all scenes
                total = len(scenes)
                done = sum(1 for s in scenes if s.status == "image_ready")
                job.progress = min(20 + int(20 * done / max(total, 1)), 40)
            except Exception as exc:
                logger.error(
                    "[image-s%s] generate_images failed: %s",
                    scene.scene_number, exc, exc_info=True,
                )
                scene.status = "failed"
                scene.error_message = str(exc)[:500]
            await db.commit()
        return context

    # ------------------------------------------------------------------
    # Stage: generate videos
    # ------------------------------------------------------------------

    async def generate_videos(
        self,
        db: AsyncSession,
        job: Job,
        scenes: list[VideoScene],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a video clip for each scene.

        For scenes ≤ 5s a single clip is generated.

        For scenes > 5s the scene is split into 5s sub-clips with
        chained last-frame seeding: each sub-clip uses the ~80% frame
        of the previous clip as its seed image, and the prompts evolve
        to tell a continuous story.  Sub-clips are merged with a 0.3s
        crossfade.
        """
        from app.services.media_generator import generate_video

        max_clip_s = 5          # Wan 2.2 practical max per clip
        crossfade_s = 0.3       # crossfade at sub-clip boundaries

        input_data = job.input_data or {}
        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        video_model = input_data.get("video_model")

        for scene in scenes:
            if scene.generated_video_path:
                continue

            scene_duration = scene.end_time - scene.start_time
            prompt = scene.visual_description or scene.lyrics_segment or ""

            try:
                if scene_duration <= max_clip_s + 0.5:
                    # ── Short scene: single clip ──────────────────────
                    duration = max(2, int(scene_duration))
                    video_path, _, _, actual_duration = await self._retry(
                        generate_video,
                        db=db, job=job, prompt=prompt,
                        scene_number=scene.scene_number,
                        reference_image_path=scene.reference_image_path,
                        provider_id=job.video_provider_id,
                        model_preference=video_model,
                        duration=duration, aspect_ratio=aspect_ratio,
                        label=f"video-s{scene.scene_number}",
                    )
                    scene.generated_video_path = video_path
                    scene.duration = actual_duration
                else:
                    # ── Long scene: sub-clip chain ────────────────────
                    scene.generated_video_path, scene.duration = (
                        await self._generate_chained_subclips(
                            db=db, job=job, scene=scene,
                            scene_duration=scene_duration,
                            max_clip_s=max_clip_s,
                            crossfade_s=crossfade_s,
                            aspect_ratio=aspect_ratio,
                        )
                    )

                scene.status = "video_ready"
            except Exception as exc:
                logger.error(
                    "[video-s%s] generate_videos failed: %s",
                    scene.scene_number, exc, exc_info=True,
                )
                scene.status = "failed"
                scene.error_message = str(exc)[:500]
            await db.commit()

        return context

    # ------------------------------------------------------------------
    # Sub-clip chaining for long scenes
    # ------------------------------------------------------------------

    async def _generate_chained_subclips(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        scene_duration: float,
        max_clip_s: int,
        crossfade_s: float,
        aspect_ratio: str,
    ) -> tuple[str, float]:
        """Split a long scene into chained sub-clips.

        Returns (relative_video_path, actual_duration).
        """
        import math
        from pathlib import Path

        input_data = job.input_data or {}
        video_model = input_data.get("video_model")

        from app.config import get_settings
        from app.services.media_generator import (
            generate_video,
            get_scene_output_dir,
        )
        from app.services.video_processor import VideoProcessor

        settings = get_settings()
        storage = Path(settings.storage_path).resolve()
        output_dir = get_scene_output_dir(str(job.id), scene.scene_number)
        output_dir.mkdir(parents=True, exist_ok=True)

        num_clips = math.ceil(scene_duration / max_clip_s)
        prompts = await self._generate_sub_scene_prompts(
            db, job, scene, num_clips,
        )

        sub_clip_paths: list[str] = []
        current_seed_path: str | None = scene.reference_image_path
        total_actual_duration = 0.0

        for i in range(num_clips):
            clip_duration = min(
                max_clip_s,
                scene_duration - i * max_clip_s,
            )
            clip_duration = max(2, int(clip_duration))

            sub_path, _, _, actual = await self._retry(
                generate_video,
                db=db, job=job,
                prompt=prompts[i],
                scene_number=scene.scene_number,
                reference_image_path=current_seed_path,
                provider_id=job.video_provider_id,
                model_preference=video_model,
                duration=clip_duration,
                aspect_ratio=aspect_ratio,
                label=f"video-s{scene.scene_number}.{i+1}/{num_clips}",
            )
            sub_clip_paths.append(str(storage / sub_path))
            total_actual_duration += actual

            # Extract ~80% frame for next clip's seed
            if i < num_clips - 1:
                seed_img = output_dir / f"seed_sub_{i + 1}.png"
                await VideoProcessor.extract_frame(
                    str(storage / sub_path), str(seed_img), ratio=0.8,
                )
                current_seed_path = str(
                    seed_img.relative_to(storage)
                )

        # Merge sub-clips with crossfade
        final_path = output_dir / "scene_video.mp4"
        if len(sub_clip_paths) == 1:
            import shutil
            shutil.copy(sub_clip_paths[0], final_path)
        else:
            await VideoProcessor.merge_with_crossfade(
                sub_clip_paths, str(final_path), crossfade_s,
            )

        relative = str(final_path.relative_to(storage))
        return relative, total_actual_duration

    async def _generate_sub_scene_prompts(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        num_clips: int,
    ) -> list[str]:
        """Use the LLM to decompose a scene into evolving sub-clip prompts.

        Falls back to the original prompt + a continuation suffix if
        the LLM is unavailable.
        """
        original_prompt = scene.visual_description or scene.lyrics_segment or ""
        image_prompt = scene.image_prompt or original_prompt

        try:
            from app.services.llm_service import LLMClient
            llm = LLMClient()

            system = (
                "You are a video director. A scene is being split into "
                f"{num_clips} consecutive sub-clips. Write a brief "
                "visual prompt for each sub-clip that tells a continuous, "
                "evolving story. Each prompt should describe what happens "
                "in that segment and flow naturally into the next. "
                "Keep each prompt under 100 words. "
                "Output ONLY a JSON array of strings."
            )
            user = (
                f"Original scene description: {original_prompt}\n"
                f"Original image prompt: {image_prompt}\n"
                f"Scene mood: {scene.mood}\n"
                f"Split into {num_clips} consecutive sub-clips."
            )
            response = await llm.generate(user, system=system)
            import json
            prompts = json.loads(response)
            if isinstance(prompts, list) and len(prompts) == num_clips:
                return [str(p) for p in prompts]
        except Exception:
            pass

        # Fallback: reuse original prompt with continuation markers
        prompts = []
        for i in range(num_clips):
            if i == 0:
                prompts.append(image_prompt)
            else:
                prompts.append(
                    f"Continuation of the scene: {original_prompt}. "
                    f"Part {i + 1} of {num_clips}."
                )
        return prompts

    # ------------------------------------------------------------------
    # Stage: render
    # ------------------------------------------------------------------

    async def render(
        self,
        db: AsyncSession,
        job: Job,
        scenes: list[VideoScene],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Final rendering: merge clips, add audio, generate preview.

        The default implementation concatenates all scene videos, adds
        the audio from ``job.input_data["audio_file"]`` (if present),
        and generates a low-res preview.
        """
        import shutil
        from pathlib import Path

        from app.config import get_settings
        from app.services.video_processor import VideoProcessor

        settings = get_settings()
        storage_path = Path(settings.storage_path).resolve()
        output_dir = storage_path / "output" / str(job.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Collect scene video paths
        segment_paths: list[str] = []
        for scene in scenes:
            if not scene.generated_video_path:
                continue
            full = storage_path / scene.generated_video_path
            if full.exists():
                segment_paths.append(str(full))

        if not segment_paths:
            raise RuntimeError("No scene videos to render")

        merged_path = output_dir / "merged.mp4"
        if len(segment_paths) == 1:
            shutil.copy(segment_paths[0], merged_path)
        else:
            await VideoProcessor.merge_videos(segment_paths, str(merged_path))

        # Add audio if available
        final_path = output_dir / "final.mp4"
        input_data = job.input_data or {}
        audio_file = input_data.get("audio_file") or context.get("audio_file")
        bgm_file = context.get("background_music")
        bgm_volume = context.get("background_music_volume", 0.3)

        if audio_file and bgm_file:
            # Mix narration + background music
            audio_path = storage_path / audio_file
            bgm_path = Path(bgm_file)
            if audio_path.exists() and bgm_path.exists():
                mixed_audio = output_dir / "mixed_audio.mp3"
                await VideoProcessor.mix_audio(
                    [str(audio_path), str(bgm_path)],
                    str(mixed_audio),
                    volumes=[context.get("audio_volume", 1.0), bgm_volume],
                )
                await VideoProcessor.add_audio(
                    str(merged_path), str(mixed_audio), str(final_path),
                    audio_volume=1.0,
                )
            elif audio_path.exists():
                await VideoProcessor.add_audio(
                    str(merged_path), str(audio_path), str(final_path),
                    audio_volume=context.get("audio_volume", 1.0),
                )
            else:
                shutil.copy(str(merged_path), str(final_path))
        elif audio_file:
            audio_path = storage_path / audio_file
            if audio_path.exists():
                await VideoProcessor.add_audio(
                    str(merged_path), str(audio_path), str(final_path),
                    audio_volume=context.get("audio_volume", 1.0),
                )
            else:
                shutil.copy(str(merged_path), str(final_path))
        elif bgm_file:
            bgm_path = Path(bgm_file)
            if bgm_path.exists():
                await VideoProcessor.add_audio(
                    str(merged_path), str(bgm_path), str(final_path),
                    audio_volume=bgm_volume,
                )
            else:
                shutil.copy(str(merged_path), str(final_path))
        else:
            shutil.copy(str(merged_path), str(final_path))

        # Preview
        preview_path = output_dir / "preview.mp4"
        try:
            await VideoProcessor.generate_preview(
                str(final_path), str(preview_path),
                width=854, height=480, fps=15, quality=28,
            )
        except Exception:
            pass

        job.output_path = str(final_path.relative_to(storage_path))
        if preview_path.exists():
            job.preview_path = str(preview_path.relative_to(storage_path))

        return {
            "output_path": job.output_path,
            "preview_path": job.preview_path,
        }

    # ------------------------------------------------------------------
    # Per-scene re-render hooks
    # ------------------------------------------------------------------

    async def rerender_scene_image(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        context: dict[str, Any],
    ) -> str | None:
        """Re-generate a single scene's image.  Returns relative path."""
        from app.services.media_generator import generate_image

        prompt = scene.image_prompt or scene.visual_description or ""
        if not prompt:
            return None
        image_path, _mid, _pid = await self._retry(
            generate_image,
            db=db, job=job, prompt=prompt,
            scene_number=scene.scene_number,
            provider_id=job.image_provider_id,
            label=f"rerender-image-s{scene.scene_number}",
        )
        scene.reference_image_path = image_path
        scene.status = "image_ready"
        scene.error_message = None
        await db.commit()
        return image_path

    async def rerender_scene_video(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        context: dict[str, Any],
    ) -> str | None:
        """Re-generate a single scene's video.  Returns relative path."""
        scene_duration = scene.end_time - scene.start_time

        if scene_duration > 5.5:
            path, duration = await self._generate_chained_subclips(
                db=db, job=job, scene=scene,
                scene_duration=scene_duration,
                max_clip_s=5, crossfade_s=0.3,
                aspect_ratio=(job.input_data or {}).get("aspect_ratio", "16:9"),
            )
            scene.generated_video_path = path
            scene.duration = duration
        else:
            from app.services.media_generator import generate_video
            duration = max(2, int(scene_duration))
            prompt = scene.visual_description or scene.lyrics_segment or ""
            input_data = job.input_data or {}
            video_path, _mid, _pid, actual_duration = await self._retry(
                generate_video,
                db=db, job=job, prompt=prompt,
                scene_number=scene.scene_number,
                reference_image_path=scene.reference_image_path,
                provider_id=job.video_provider_id,
                model_preference=input_data.get("video_model"),
                duration=duration,
                aspect_ratio=input_data.get("aspect_ratio", "16:9"),
                label=f"rerender-video-s{scene.scene_number}",
            )
            scene.generated_video_path = video_path
            scene.duration = actual_duration

        scene.status = "video_ready"
        scene.error_message = None
        await db.commit()
        return scene.generated_video_path

    # ------------------------------------------------------------------
    # UI metadata
    # ------------------------------------------------------------------

    def get_ui_schema(self) -> dict[str, Any]:
        """Return a JSON schema describing the template's editor UI.

        The default auto-generates from the template definition's inputs.
        """
        return {}

    def get_editor_panels(self) -> list[dict[str, Any]]:
        """Return editor panels for the scene editor.

        Default panels: scenes grid, timeline, export.
        """
        return [
            {"id": "scenes", "label": "Scenes", "component": "SceneGrid"},
            {"id": "timeline", "label": "Timeline", "component": "Timeline"},
            {"id": "export", "label": "Export", "component": "ExportPanel"},
        ]

    def get_export_options_schema(self) -> dict[str, Any]:
        """Return a JSON schema for template-specific export options."""
        return {}


async def _import_scene_asset(
    db, job, file_path, name, file_type, scene_number,
) -> None:
    """Import a generated scene asset into the media library."""
    if not file_path:
        return
    try:
        from pathlib import Path
        from app.config import get_settings
        from app.services.auto_import import (
            _create_asset_from_file,
            _get_or_create_folder,
        )

        settings = get_settings()
        storage = Path(settings.storage_path).resolve()
        full_path = storage / file_path
        if not full_path.exists():
            return

        # Create/use a per-job folder under /Generated
        gen_folder = await _get_or_create_folder(
            user_id=job.user_id,
            name="Generated",
            parent_id=None,
            db=db,
        )
        job_folder = await _get_or_create_folder(
            user_id=job.user_id,
            name=job.title or f"Job-{str(job.id)[:8]}",
            parent_id=gen_folder.id,
            db=db,
        )

        await _create_asset_from_file(
            user_id=job.user_id,
            folder_id=job_folder.id,
            file_path=full_path,
            name=name,
            file_type=file_type,
            source_job_id=job.id,
            db=db,
        )
    except Exception:
        pass  # Non-critical — don't fail the pipeline if import fails
