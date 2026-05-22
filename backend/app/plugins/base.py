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

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

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

        for scene in scenes:
            if scene.reference_image_path:
                continue
            prompt = scene.image_prompt or scene.visual_description or ""
            if not prompt:
                continue
            try:
                image_path, _media_id, _provider_id = await generate_image(
                    db=db,
                    job=job,
                    prompt=prompt,
                    scene_number=scene.scene_number,
                    provider_id=job.image_provider_id,
                )
                scene.reference_image_path = image_path
                scene.status = "image_ready"
            except Exception as exc:
                scene.status = "failed"
                scene.error_message = str(exc)
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

        The default implementation iterates over *scenes* and calls the
        core video generator using the scene's reference image and
        visual description.
        """
        from app.services.media_generator import generate_video

        input_data = job.input_data or {}
        aspect_ratio = input_data.get("aspect_ratio", "16:9")

        for scene in scenes:
            if scene.generated_video_path:
                continue
            duration = max(2, min(int(scene.end_time - scene.start_time), 5))
            prompt = scene.visual_description or scene.lyrics_segment or ""
            try:
                video_path, _media_id, _provider_id, actual_duration = (
                    await generate_video(
                        db=db,
                        job=job,
                        prompt=prompt,
                        scene_number=scene.scene_number,
                        reference_image_path=scene.reference_image_path,
                        provider_id=job.video_provider_id,
                        duration=duration,
                        aspect_ratio=aspect_ratio,
                    )
                )
                scene.generated_video_path = video_path
                scene.status = "video_ready"
                scene.duration = actual_duration
            except Exception as exc:
                scene.status = "failed"
                scene.error_message = str(exc)
            await db.commit()
        return context

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

        # Stretch each scene clip to match its intended duration, then merge.
        # Video models (Wan2.2, Poe Veo, etc.) produce short clips (3-8s),
        # but scenes may need much longer (e.g. 115s).  We loop the clip
        # to fill the scene duration so the final video matches the timeline.
        stretched_paths: list[str] = []
        for scene in scenes:
            if not scene.generated_video_path:
                continue
            full = storage_path / scene.generated_video_path
            if not full.exists():
                continue

            scene_duration = scene.end_time - scene.start_time
            clip_duration = scene.duration or scene_duration

            if clip_duration >= scene_duration - 0.5:
                # Clip is already long enough — use as-is
                stretched_paths.append(str(full))
            else:
                # Stretch (loop) the clip to fill the scene duration
                stretched = output_dir / f"scene_{scene.scene_number:03d}_stretched.mp4"
                await VideoProcessor.stretch_to_duration(
                    str(full), scene_duration, str(stretched),
                )
                stretched_paths.append(str(stretched))

        if not stretched_paths:
            raise RuntimeError("No scene videos to render")

        merged_path = output_dir / "merged.mp4"
        if len(stretched_paths) == 1:
            shutil.copy(stretched_paths[0], merged_path)
        else:
            await VideoProcessor.merge_videos(stretched_paths, str(merged_path))

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
        image_path, _mid, _pid = await generate_image(
            db=db, job=job, prompt=prompt,
            scene_number=scene.scene_number,
            provider_id=job.image_provider_id,
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
        from app.services.media_generator import generate_video

        input_data = job.input_data or {}
        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        duration = max(2, min(int(scene.end_time - scene.start_time), 5))
        prompt = scene.visual_description or scene.lyrics_segment or ""

        video_path, _mid, _pid, actual_duration = await generate_video(
            db=db, job=job, prompt=prompt,
            scene_number=scene.scene_number,
            reference_image_path=scene.reference_image_path,
            provider_id=job.video_provider_id,
            duration=duration, aspect_ratio=aspect_ratio,
        )
        scene.generated_video_path = video_path
        scene.status = "video_ready"
        scene.duration = actual_duration
        scene.error_message = None
        await db.commit()
        return video_path

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
