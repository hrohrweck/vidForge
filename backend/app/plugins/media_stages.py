"""Default media-generation stages for template plugins."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any, cast

from app.plugins.enrichment import _generate_llm_text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import Job, VideoScene

_module_logger = logging.getLogger(__name__)


class _BaseLoggerProxy:
    def __getattr__(self, name: str) -> Any:
        base_module = sys.modules.get("app.plugins.base")
        return getattr(getattr(base_module, "logger", _module_logger), name)


logger = _BaseLoggerProxy()


async def _import_scene_asset(*args: Any, **kwargs: Any) -> Any:
    base_module = sys.modules.get("app.plugins.base")
    target = getattr(base_module, "_import_scene_asset", None)
    if target is not None and target is not _import_scene_asset:
        return await target(*args, **kwargs)
    return None


class MediaStagesMixin:
    """Default image, video, chaining, and render stages shared by plugins."""

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
        from pathlib import Path

        from app.services.media_generator import generate_image

        input_data = job.input_data or {}
        image_model = input_data.get("image_model")

        from app.services.model_config_service import ModelConfigService
        image_model_config = None
        if image_model:
            image_model_config = await ModelConfigService.resolve_model_config(db, image_model)

        # Extract avatar reference images from context
        avatars = context.get("avatars", [])
        avatar_ref_path: str | None = None
        if avatars:
            first = avatars[0]
            avatar_ref_path = first.get("primary_image_path")
            if not avatar_ref_path:
                logger.warning(
                    "Avatar %s has no primary_image_path, "
                    "falling back to text-to-image",
                    first.get("name", first.get("id", "unknown")),
                )
                avatar_ref_path = None
            elif not Path(avatar_ref_path).exists():
                logger.warning(
                    "Avatar %s primary image not found on disk at %s, "
                    "falling back to text-to-image",
                    first.get("name", first.get("id", "unknown")),
                    avatar_ref_path,
                )
                avatar_ref_path = None

        await cast(Any, self)._generate_object_references(db, job, context)

        for scene in scenes:
            if scene.reference_image_path:
                continue
            prompt = scene.image_prompt or scene.visual_description or ""
            if not prompt:
                continue

            # Inject object visual properties for this scene
            objects_ctx = context.get("objects", [])
            object_selections_ctx = context.get("object_selections", [])
            if objects_ctx and object_selections_ctx:
                scene_objects = [
                    sel for sel in object_selections_ctx
                    if scene.scene_number in sel.get("scenes", [])
                ]
                if scene_objects:
                    best = max(scene_objects, key=lambda s: s.get("importance_score", 0))
                    obj = next(
                        (o for o in objects_ctx if o.get("name") == best.get("object_name")),
                        None,
                    )
                    if obj and obj.get("primary_image_path"):
                        obj_visual = obj.get("visual_properties", {})
                        if obj_visual:
                            props_str = ", ".join(
                                f"{k}={v}" for k, v in obj_visual.items()
                            )
                            prompt = f"{prompt} [Object reference: {props_str}]"

            try:
                image_path, _media_id, _provider_id, image_cost = await cast(Any, self)._retry(
                    generate_image,
                    db=db,
                    job=job,
                    prompt=prompt,
                    scene_number=scene.scene_number,
                    model_preference=image_model,
                    provider_id=job.image_provider_id,
                    reference_image_path=avatar_ref_path,
                    reference_image_strength=0.75,
                    label=f"image-s{scene.scene_number}",
                )
                if image_cost:
                    from app.services.cost_estimator import record_media_generation_cost
                    try:
                        await record_media_generation_cost(
                            db, job, image_model_config, "image"
                        )
                    except Exception as cost_exc:
                        logger.warning(
                            "[image-s%s] Failed to record generation cost: %s",
                            scene.scene_number, cost_exc,
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
                # If we were using a reference image, try T2I fallback
                if avatar_ref_path:
                    logger.warning(
                        "[image-s%s] img2img failed (retries exhausted), "
                        "falling back to T2I: %s",
                        scene.scene_number, exc,
                    )
                    try:
                        image_path, _media_id, _provider_id, image_cost = await cast(Any, self)._retry(
                            generate_image,
                            db=db,
                            job=job,
                            prompt=prompt,
                            scene_number=scene.scene_number,
                            model_preference=image_model,
                            provider_id=job.image_provider_id,
                            label=f"image-s{scene.scene_number}-t2i",
                        )
                        if image_cost:
                            from app.services.cost_estimator import record_media_generation_cost
                            try:
                                await record_media_generation_cost(
                                    db, job, image_model_config, "image"
                                )
                            except Exception as cost_exc:
                                logger.warning(
                                    "[image-s%s] Failed to record generation cost: %s",
                                    scene.scene_number, cost_exc,
                                )
                        scene.reference_image_path = image_path
                        scene.status = "image_ready"
                        # Auto-import to media library
                        await _import_scene_asset(
                            db, job, scene.reference_image_path,
                            f"scene-{scene.scene_number}-image",
                            "image", scene.scene_number,
                        )
                        # Update progress
                        total = len(scenes)
                        done = sum(1 for s in scenes if s.status == "image_ready")
                        job.progress = min(20 + int(20 * done / max(total, 1)), 40)
                        continue  # Skip the failure marking below
                    except Exception as fallback_exc:
                        logger.error(
                            "[image-s%s] T2I fallback also failed: %s",
                            scene.scene_number, fallback_exc,
                        )

                # Original error handling (mark scene failed)
                logger.error(
                    "[image-s%s] generate_images failed: %s",
                    scene.scene_number, exc, exc_info=True,
                )
                scene.status = "failed"
                scene.error_message = str(exc)[:500]
            await db.commit()
        return context

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

        from app.services.model_config_service import ModelConfigService
        video_model_config = None
        if video_model:
            video_model_config = await ModelConfigService.resolve_model_config(db, video_model)

        # Extract avatar context for sub-scene prompt hardening
        avatars = context.get("avatars", [])

        for scene in scenes:
            if scene.generated_video_path:
                continue

            scene_duration = scene.end_time - scene.start_time
            prompt = scene.visual_description or scene.lyrics_segment or ""

            # Inject object visual properties for this scene (short clip path)
            objects_ctx = context.get("objects", [])
            object_selections_ctx = context.get("object_selections", [])
            if objects_ctx and object_selections_ctx and prompt:
                scene_objs = [
                    sel for sel in object_selections_ctx
                    if scene.scene_number in sel.get("scenes", [])
                ]
                if scene_objs:
                    best = max(scene_objs, key=lambda s: s.get("importance_score", 0))
                    obj = next(
                        (o for o in objects_ctx if o.get("name") == best.get("object_name")),
                        None,
                    )
                    if obj and obj.get("primary_image_path") and obj.get("visual_properties"):
                        props_str = ", ".join(
                            f"{k}={v}" for k, v in obj["visual_properties"].items()
                        )
                        prompt = f"{prompt} [Object reference: {props_str}]"

            from app.database import ErrorOrigin, ErrorSeverity
            from app.services.error_capture import log_user_error

            try:
                if scene_duration <= max_clip_s + 0.5:
                    # ── Short scene: single clip ──────────────────────
                    duration = max(2, int(scene_duration))
                    video_path, _, _, actual_duration, warning, video_cost = await cast(Any, self)._retry(
                        generate_video,
                        db=db, job=job, prompt=prompt,
                        scene_number=scene.scene_number,
                        reference_image_path=scene.reference_image_path,
                        provider_id=job.video_provider_id,
                        model_preference=video_model,
                        duration=duration, aspect_ratio=aspect_ratio,
                        label=f"video-s{scene.scene_number}",
                    )
                    if video_cost:
                        from app.services.cost_estimator import record_media_generation_cost
                        try:
                            await record_media_generation_cost(
                                db, job, video_model_config, "video", duration=duration
                            )
                        except Exception as cost_exc:
                            logger.warning(
                                "[video-s%s] Failed to record generation cost: %s",
                                scene.scene_number, cost_exc,
                            )
                    scene.generated_video_path = video_path
                    scene.duration = actual_duration
                    if warning:
                        if scene.warnings is None:
                            scene.warnings = []
                        scene.warnings.append(warning)
                else:
                    # ── Long scene: sub-clip chain ────────────────────
                    scene.generated_video_path, scene.duration = (
                        await cast(Any, self)._generate_chained_subclips(
                            db=db, job=job, scene=scene,
                            scene_duration=scene_duration,
                            max_clip_s=max_clip_s,
                            crossfade_s=crossfade_s,
                            aspect_ratio=aspect_ratio,
                            avatars=avatars,
                            objects=context.get("objects", []),
                            video_model_config=video_model_config,
                        )
                    )

                scene.status = "video_ready"
                scene.error_message = None
            except Exception as exc:
                logger.error(
                    "[video-s%s] generate_videos failed: %s",
                    scene.scene_number, exc, exc_info=True,
                )
                scene.status = "failed"
                scene.error_message = str(exc)[:500]
                details = {"scene_number": scene.scene_number, "model": video_model}
                result = getattr(exc, "result", None)
                if result is not None:
                    details.update(
                        {
                            "actual_frames": getattr(result, "actual_frames", None),
                            "expected_frames": getattr(result, "expected_frames", None),
                        }
                    )
                await log_user_error(
                    db,
                    user_id=job.user_id,
                    severity=ErrorSeverity.ERROR,
                    origin=ErrorOrigin.VIDEO_GENERATION,
                    message=str(exc),
                    details=details,
                    source_id=scene.id,
                    source_type="scene",
                )

            await db.commit()

        return context

    async def _generate_chained_subclips(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        scene_duration: float,
        max_clip_s: int,
        crossfade_s: float,
        aspect_ratio: str,
        avatars: list[dict[str, Any]] | None = None,
        objects: list[dict[str, Any]] | None = None,
        video_model_config: Any | None = None,
    ) -> tuple[str, float]:
        """Split a long scene into chained sub-clips.

        Returns (relative_video_path, actual_duration).
        """
        import inspect
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
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        num_clips = math.ceil(scene_duration / max_clip_s)
        prompt_kwargs: dict[str, Any] = {"avatars": avatars}
        try:
            prompt_params = inspect.signature(self._generate_sub_scene_prompts).parameters
        except (TypeError, ValueError):
            prompt_params = {}
        if "objects" in prompt_params:
            prompt_kwargs["objects"] = objects
        prompts = await self._generate_sub_scene_prompts(
            db, job, scene, num_clips, **prompt_kwargs,
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

            sub_path, _, _, actual, warning, sub_cost = await cast(Any, self)._retry(
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
            if sub_cost:
                from app.services.cost_estimator import record_media_generation_cost
                try:
                    await record_media_generation_cost(
                        db, job, video_model_config, "video", duration=clip_duration
                    )
                except Exception as cost_exc:
                    logger.warning(
                        "[video-s%s.%s] Failed to record generation cost: %s",
                        scene.scene_number, i + 1, cost_exc,
                    )
            sub_clip_paths.append(str(storage / sub_path))
            total_actual_duration += actual
            if warning:
                if scene.warnings is None:
                    scene.warnings = []
                scene.warnings.append(warning)

            # Extract ~80% frame for next clip's seed
            if i < num_clips - 1:
                seed_img = output_dir / f"seed_sub_{i + 1}.png"
                await VideoProcessor.extract_frame(
                    str(storage / sub_path), str(seed_img), ratio=0.8,
                )
                current_seed_path = str(
                    seed_img.relative_to(storage)
                )
                # Ensure consistent path separators
                current_seed_path = current_seed_path.replace("\\", "/")

        # Merge sub-clips with crossfade
        final_path = output_dir / "scene_video.mp4"
        if final_path.exists():
            final_path.unlink()  # Remove stale file from previous attempt
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
        avatars: list[dict[str, Any]] | None = None,
        objects: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """Use the LLM to decompose a scene into evolving sub-clip prompts.

        Falls back to the original prompt + a continuation suffix if
        the LLM is unavailable.

        When avatar characters are provided, their descriptions are included
        in the system prompt so the LLM maintains character consistency across
        sub-clips.
        """
        original_prompt = scene.visual_description or scene.lyrics_segment or ""
        image_prompt = scene.image_prompt or original_prompt
        input_data = job.input_data or {}

        # Build character context string from avatars
        character_context = ""
        if avatars:
            active = [
                a for a in avatars
                if not a.get("deleted") and a.get("name")
            ]
            if active:
                chars = []
                for a in active:
                    parts = [a["name"]]
                    if a.get("gender"):
                        parts.append(f"({a['gender']})")
                    if a.get("role"):
                        parts.append(f"– {a['role']}")
                    if a.get("bio"):
                        parts.append(f": {a['bio']}")
                    chars.append(" ".join(parts))
                character_context = (
                    "CHARACTERS (must remain visually consistent across "
                    "all sub-clips):\n" + "\n".join(f"  – {c}" for c in chars)
                )

        # Build object context string from objects with reference images
        object_context = ""
        if objects:
            ref_objects = [
                o for o in objects
                if o.get("primary_image_path") and o.get("visual_properties")
            ]
            if ref_objects:
                obj_lines = []
                for o in ref_objects:
                    name = o.get("name", "unknown")
                    props = o.get("visual_properties", {})
                    props_str = ", ".join(f"{k}={v}" for k, v in props.items())
                    obj_lines.append(f"  – {name}: {props_str}")
                object_context = (
                    "OBJECT REFERENCES (maintain visual consistency for "
                    "these objects across all sub-clips):\n"
                    + "\n".join(obj_lines)
                )

        try:
            from app.services.llm_service import resolve_llm
            text_model = input_data.get("text_model")
            llm = await resolve_llm(text_model or "", db)

            system = (
                "You are a video director. A scene is being split into "
                f"{num_clips} consecutive sub-clips. Write a brief "
                "visual prompt for each sub-clip that tells a continuous, "
                "evolving story. Each prompt should describe what happens "
                "in that segment and flow naturally into the next. "
                "Keep each prompt under 100 words. "
                "Output ONLY a JSON array of strings."
            )
            if character_context:
                system = character_context + "\n\n" + system
            if object_context:
                system = object_context + "\n\n" + system

            user = (
                f"Original scene description: {original_prompt}\n"
                f"Original image prompt: {image_prompt}\n"
                f"Scene mood: {scene.mood}\n"
                f"Split into {num_clips} consecutive sub-clips."
            )
            response = await _generate_llm_text(
                llm,
                prompt=user,
                system=system,
                model=text_model or "",
            )
            import json
            prompts = json.loads(response)
            if isinstance(prompts, list) and len(prompts) == num_clips:
                return [str(p) for p in prompts]
        except Exception as llm_exc:
            logger.warning(
                "[scene-%s] Failed to generate sub-scene prompts via LLM: %s",
                scene.scene_number, llm_exc,
            )

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

        # Check if any scene needs padding
        any_needs_padding = False
        for scene in scenes:
            if scene.warnings:
                for w in scene.warnings:
                    if "aspect ratio" in w.lower():
                        any_needs_padding = True
                        break
            if any_needs_padding:
                break

        input_data = job.input_data or {}
        target_aspect = input_data.get("aspect_ratio", "16:9")

        # Collect scene video paths
        segment_paths: list[str] = []
        for scene in scenes:
            if not scene.generated_video_path:
                continue
            full = storage_path / scene.generated_video_path
            if full.exists():
                if any_needs_padding:
                    padded_path = output_dir / f"padded_scene_{scene.scene_number}.mp4"
                    await VideoProcessor.pad_to_aspect_ratio(
                        str(full), str(padded_path), target_aspect
                    )
                    scene.generated_video_path = str(padded_path.relative_to(storage_path))
                    segment_paths.append(str(padded_path))
                else:
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
