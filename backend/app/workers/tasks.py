"""
Celery task definitions for VidForge.

Every task is a thin synchronous shim that delegates to an async helper
executed on the shared WorkerContext event loop.  The engine, session
factory, and Redis client are created once per worker process (not per
task invocation) — see ``app.workers.context``.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.database import Job, Provider, Template
from app.services.budget_tracker import BudgetTracker
from app.services.job_router import JobRouter
from app.services.video_generator import process_job_video
from app.services.worker_registry import WorkerRegistry
from app.workers.celery_app import celery_app
from app.workers.context import ctx

logger = logging.getLogger(__name__)

settings = get_settings()

COMFYUI_SEMAPHORE_KEY = "comfyui:processing"
COMFYUI_MAX_CONCURRENT = getattr(settings, "comfyui_max_concurrent", 1)
TASK_TIME_LIMIT = getattr(settings, "task_time_limit", 172800)


# ======================================================================
# Shared helpers (async, use ctx resources)
# ======================================================================


async def broadcast_update(job_id: str, message: dict) -> None:
    """Publish a job-status update to Redis Pub/Sub."""
    try:
        await ctx.redis.publish(f"job:{job_id}", json.dumps(message))
    except Exception:
        logger.warning("Failed to broadcast update for job %s", job_id, exc_info=True)


async def progress_callback(job_id: str, progress: int, message: str) -> None:
    """Progress callback suitable for passing to video/audio services."""
    await broadcast_update(
        job_id, {"type": "progress", "progress": progress, "message": message}
    )


async def update_job_status(
    job_id: UUID,
    status: str,
    progress: int = 0,
    error_message: str | None = None,
    output_path: str | None = None,
    preview_path: str | None = None,
    provider_id: UUID | None = None,
    estimated_cost: Decimal | None = None,
    actual_cost: Decimal | None = None,
) -> None:
    """Persist a job-status change to the database and broadcast it."""
    async with ctx.session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = status
        job.progress = progress
        if error_message is not None:
            job.error_message = error_message
        if output_path is not None:
            job.output_path = output_path
        if preview_path is not None:
            job.preview_path = preview_path
        if provider_id is not None:
            job.provider_id = provider_id
        if estimated_cost is not None:
            job.estimated_cost = estimated_cost
        if actual_cost is not None:
            job.actual_cost = actual_cost

        if status == "processing" and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in ("completed", "failed") and not job.completed_at:
            job.completed_at = datetime.utcnow()

        await db.commit()

    payload = {
        "type": "status_update",
        "status": status,
        "progress": progress,
        "error_message": error_message,
        "output_path": output_path,
        "preview_path": preview_path,
    }
    await broadcast_update(str(job_id), payload)


async def get_template_name(db, template_id: UUID | None) -> str:
    """Look up a template name by ID (uses the caller's session)."""
    if template_id is None:
        return "prompt_to_video"
    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    return template.name if template else "prompt_to_video"


def _as_decimal(value: float | int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


# ======================================================================
# ComfyUI concurrency semaphore (async Redis)
# ======================================================================


class ComfyUISemaphore:
    """Redis-based semaphore for limiting concurrent local ComfyUI jobs.

    Uses the shared ``ctx.redis`` (async) client — no per-instance
    connection is created.
    """

    def __init__(self, key: str, max_concurrent: int):
        self._key = key
        self._max = max_concurrent
        self._acquired = False

    async def acquire(self, job_id: str) -> bool:
        current = int(await ctx.redis.get(self._key) or 0)
        if current < self._max:
            await ctx.redis.incr(self._key)
            self._acquired = True
            return True
        return False

    async def release(self) -> None:
        if self._acquired:
            current = int(await ctx.redis.get(self._key) or 0)
            if current > 0:
                await ctx.redis.decr(self._key)
            self._acquired = False


# ======================================================================
# Provider dispatch helpers
# ======================================================================


async def _resolve_provider_for_job(
    db, job: Job, workflow: dict, preference: str
) -> tuple:
    router = JobRouter(db)

    if job.provider_id:
        provider = await router.get_provider_record(job.provider_id)
        if not provider:
            raise ValueError(f"Assigned provider {job.provider_id} no longer exists")
        if not provider.is_active:
            raise ValueError(f"Assigned provider '{provider.name}' is inactive")

        provider_instance = await router.get_provider_instance(provider.id)
        estimated_cost = Decimal(str(await provider_instance.estimate_cost(workflow)))

        if provider.provider_type == "runpod":
            allowed, reason = await router.budget_tracker.check_budget(
                provider.id, estimated_cost
            )
            if not allowed:
                raise ValueError(
                    f"Assigned provider '{provider.name}' unavailable: {reason}"
                )
        return provider, provider_instance, estimated_cost, router, "Assigned provider"

    provider, provider_instance, reason = await router.select_provider(
        preference=preference, workflow=workflow,
    )
    estimated_cost = Decimal(str(await provider_instance.estimate_cost(workflow)))
    return provider, provider_instance, estimated_cost, router, reason


async def _run_local_job(
    job_id: str, template_name: str | None, input_data: dict,
) -> tuple[str, str | None]:
    video_path, preview_path = await process_job_video(
        job_id=job_id,
        template_name=template_name,
        input_data=input_data,
        progress_callback=lambda p, m: progress_callback(job_id, p, m),
    )
    relative_video = str(Path(video_path).relative_to(settings.storage_path))
    relative_preview = (
        str(Path(preview_path).relative_to(settings.storage_path))
        if preview_path
        else None
    )
    return relative_video, relative_preview


async def _run_runpod_job(
    job_id: str, workflow: dict, provider_instance,
) -> tuple[str, str | None]:
    run_id = await provider_instance.queue_prompt(workflow)
    result = await provider_instance.wait_for_completion(
        run_id,
        progress_callback=lambda p, m: ctx.run(
            broadcast_update(job_id, {"type": "progress", "progress": p, "message": m})
        ),
    )
    output_data = await provider_instance.get_output(result)
    if not output_data:
        raise RuntimeError("RunPod returned no output data")

    output_dir = Path(settings.storage_path) / "output" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "video.mp4"
    output_path.write_bytes(output_data)
    return str(output_path), None


async def _run_poe_job(
    job_id: str,
    provider_instance,
    model_preference: str | None,
    input_data: dict,
    db,
) -> str:
    from app.database import PoeModel

    prompt = input_data.get("prompt", "")
    negative_prompt = input_data.get("negative_prompt", "")

    result = await db.execute(
        select(PoeModel).where(
            PoeModel.provider_id == provider_instance.provider_id,
            PoeModel.is_active,
        )
    )
    available_models = list(result.scalars().all())
    if not available_models:
        raise ValueError(
            f"No Poe models configured for provider {provider_instance.provider_id}"
        )

    selected_model = None
    if model_preference:
        for m in available_models:
            if m.id == UUID(model_preference) or m.model_id == model_preference:
                selected_model = m
                break
    if not selected_model:
        selected_model = available_models[0]

    poe_model_id = selected_model.model_id
    is_image = selected_model.modality == "image"
    duration = input_data.get("duration", 10)
    aspect_ratio = input_data.get("aspect_ratio", "16:9")
    resolution = input_data.get("resolution", "1080p")

    output_path = Path(settings.storage_path) / "output" / job_id
    output_path.mkdir(parents=True, exist_ok=True)

    if is_image:
        output_file = output_path / "image.png"
        _, image_data = await provider_instance.generate_image(
            prompt=prompt,
            model=poe_model_id,
            aspect_ratio=aspect_ratio,
            quality=input_data.get("quality", "high"),
            negative_prompt=negative_prompt,
        )
        if image_data:
            output_file.write_bytes(image_data)
        return str(output_path.relative_to(settings.storage_path)) + "/image.png"
    else:
        output_file = output_path / "video.mp4"
        _, video_data = await provider_instance.generate_video(
            prompt=prompt,
            model=poe_model_id,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            negative_prompt=negative_prompt,
        )
        if video_data:
            output_file.write_bytes(video_data)
        return str(output_path.relative_to(settings.storage_path)) + "/video.mp4"


# ======================================================================
# Task 1: process_video_job
# ======================================================================


@celery_app.task(bind=True, time_limit=TASK_TIME_LIMIT)
def process_video_job(self, job_id: str, provider_preference: str = "auto") -> dict:
    return ctx.run(_process_video_job(job_id, provider_preference))


async def _process_video_job(job_id: str, provider_preference: str = "auto") -> dict:
    job_uuid = UUID(job_id)

    await update_job_status(job_uuid, "queued", 0)

    async with ctx.session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_uuid))
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        input_data = job.input_data or {}
        template_name = await get_template_name(db, job.template_id)
        preference = job.provider_preference or provider_preference

        if not job.provider_preference:
            job.provider_preference = preference
        model_preference = job.model_preference

        result = await db.execute(select(Template).where(Template.id == job.template_id))
        template = result.scalar_one_or_none()
        workflow = template.config if template else {}

        router = None
        semaphore = None
        provider_record = None
        estimated_cost = None
        relative_video: str | None = None
        relative_preview: str | None = None

        try:
            (
                provider_record,
                provider_instance,
                estimated_cost,
                router,
                _,
            ) = await _resolve_provider_for_job(db, job, workflow, preference)

            job.provider_id = provider_record.id
            job.provider_type = provider_record.provider_type
            job.provider_preference = preference
            if job.estimated_cost is None:
                job.estimated_cost = estimated_cost
            await db.commit()

            await update_job_status(
                job_uuid, "processing", 0,
                provider_id=provider_record.id,
                estimated_cost=estimated_cost,
            )

            started_at = datetime.utcnow()

            if provider_record.provider_type == "comfyui_direct":
                semaphore = ComfyUISemaphore(
                    key=f"{COMFYUI_SEMAPHORE_KEY}:{provider_record.id}",
                    max_concurrent=provider_record.config.get(
                        "max_concurrent_jobs", COMFYUI_MAX_CONCURRENT
                    ),
                )
                acquired = await semaphore.acquire(job_id)
                if not acquired:
                    await update_job_status(
                        job_uuid, "failed", 0,
                        error_message="GPU queue is full. Job will be retried.",
                    )
                    return {"status": "failed", "error": "Queue full", "job_id": job_id}

                relative_video, relative_preview = await _run_local_job(
                    job_id, template_name, input_data,
                )

            elif provider_record.provider_type == "poe":
                relative_video = await _run_poe_job(
                    job_id, provider_instance, model_preference, input_data, db,
                )
                relative_preview = None

            elif provider_record.provider_type == "runpod":
                run_result_video, run_result_preview = await _run_runpod_job(
                    job_id, workflow, provider_instance,
                )
                if run_result_video.startswith(settings.storage_path):
                    relative_video = str(
                        Path(run_result_video).relative_to(settings.storage_path)
                    )
                else:
                    relative_video = str(run_result_video)
                if run_result_preview:
                    relative_preview = (
                        str(Path(run_result_preview).relative_to(settings.storage_path))
                        if run_result_preview.startswith(settings.storage_path)
                        else str(run_result_preview)
                    )
                else:
                    relative_preview = None

                # Record runpod spend immediately (has its own cost tracking)
                actual_cost = _as_decimal(estimated_cost)
                if actual_cost:
                    await router.budget_tracker.record_spend(
                        provider_record.id, actual_cost
                    )
            else:
                raise ValueError(
                    f"Unknown provider type: {provider_record.provider_type}"
                )

            # --- Record cost for all provider types -----------------------
            actual_cost = _as_decimal(estimated_cost)
            duration_seconds = max(
                1, int((datetime.utcnow() - started_at).total_seconds())
            )
            budget_tracker = BudgetTracker(db)
            await budget_tracker.record_spend(
                provider_record.id,
                job_uuid,
                actual_cost,
                duration_seconds=duration_seconds,
                gpu_type=provider_record.config.get("gpu_type"),
            )

            await update_job_status(
                job_uuid, "completed", 100,
                output_path=relative_video,
                preview_path=relative_preview,
                actual_cost=actual_cost,
            )
            return {"status": "completed", "job_id": job_id}

        except Exception as exc:
            error_message = str(exc)
            await update_job_status(job_uuid, "failed", 0, error_message=error_message)
            return {"status": "failed", "error": error_message, "job_id": job_id}

        finally:
            if semaphore:
                await semaphore.release()
            if router is not None:
                try:
                    await router.shutdown()
                except Exception:
                    pass


# ======================================================================
# Task 2: send_heartbeat
# ======================================================================


@celery_app.task
def send_heartbeat() -> dict:
    return ctx.run(_send_heartbeat())


async def _send_heartbeat() -> dict:
    async with ctx.session_factory() as db:
        registry = WorkerRegistry(db)

        result = await db.execute(
            select(Provider).where(
                Provider.provider_type == "comfyui_direct", Provider.is_active
            )
        )
        provider = result.scalar_one_or_none()

        if provider:
            await registry.register(
                worker_id=settings.worker_id,
                name=settings.worker_name,
                provider_id=provider.id,
                capabilities={
                    "gpu": "Radeon 890M",
                    "max_concurrent": settings.comfyui_max_concurrent,
                },
            )
            await registry.heartbeat(settings.worker_id)

    return {"status": "ok"}


# ======================================================================
# Task 3: cleanup_stale_workers
# ======================================================================


@celery_app.task
def cleanup_stale_workers() -> dict:
    return ctx.run(_cleanup_stale_workers())


async def _cleanup_stale_workers() -> dict:
    async with ctx.session_factory() as db:
        registry = WorkerRegistry(db)
        count = await registry.cleanup_stale_workers()
        if count > 0:
            logger.info("[Worker] Cleaned up %d stale workers", count)
    return {"cleaned": count}


# ======================================================================
# Task 4: reset_daily_budgets
# ======================================================================


@celery_app.task
def reset_daily_budgets() -> dict:
    return ctx.run(_reset_daily_budgets())


async def _reset_daily_budgets() -> dict:
    async with ctx.session_factory() as db:
        result = await db.execute(select(Provider))
        providers = result.scalars().all()

        tracker = BudgetTracker(db)
        for provider in providers:
            await tracker.reset_provider_spend(provider.id)

    return {"reset_count": len(providers)}


# ======================================================================
# Task 5: generate_preview
# ======================================================================


@celery_app.task
def generate_preview(job_id: str) -> dict:
    return ctx.run(_generate_preview(job_id))


async def _generate_preview(job_id: str) -> dict:
    from app.services.video_processor import VideoProcessor

    video_path = Path(settings.storage_path) / "output" / job_id / "video.mp4"
    preview_path = Path(settings.storage_path) / "output" / job_id / "preview.mp4"

    if not video_path.exists():
        return {"status": "failed", "error": "Video not found", "job_id": job_id}

    await VideoProcessor.generate_preview(
        str(video_path),
        str(preview_path),
        width=settings.preview_width,
        height=settings.preview_height,
        fps=settings.preview_fps,
        quality=settings.preview_quality,
    )

    return {"status": "completed", "job_id": job_id, "preview": str(preview_path)}


# ======================================================================
# Task 6: merge_videos
# ======================================================================


@celery_app.task
def merge_videos(job_id: str, segment_paths: list[str]) -> dict:
    return ctx.run(_merge_videos(job_id, segment_paths))


async def _merge_videos(job_id: str, segment_paths: list[str]) -> dict:
    from app.services.video_processor import VideoProcessor

    output_path = Path(settings.storage_path) / "output" / job_id / "merged.mp4"
    await VideoProcessor.merge_videos(segment_paths, str(output_path))
    return {
        "status": "completed",
        "job_id": job_id,
        "segments": len(segment_paths),
        "output": str(output_path),
    }


# ======================================================================
# Task 7: process_scene_video_job
# ======================================================================


@celery_app.task(bind=True, time_limit=TASK_TIME_LIMIT)
def process_scene_video_job(self, job_id: str, stage: str = "planning") -> dict:
    return ctx.run(_process_scene_video_job(job_id, stage))


async def _process_scene_video_job(job_id: str, stage: str = "planning") -> dict:
    async with ctx.session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return {"status": "failed", "error": "Job not found"}

        await update_job_status(job.id, "processing", progress=0)

        if stage == "planning":
            return await _stage_planning(db, job)
        elif stage == "generating_images":
            return await _stage_generating_images(db, job)
        elif stage == "generating_videos":
            return await _stage_generating_videos(db, job)
        elif stage == "rendering":
            return await _stage_rendering(db, job)
        else:
            return {"status": "failed", "error": f"Unknown stage: {stage}"}


# ======================================================================
# Scene-based pipeline stages
# ======================================================================


async def _stage_planning(db, job) -> dict:
    from app.database import VideoScene
    from app.services.lyrics_extractor import LyricsExtractor
    from app.services.music_video_planner import MusicVideoPlanner

    await broadcast_update(str(job.id), {
        "stage": "planning", "progress": 10,
        "status": "Processing lyrics...",
    })

    input_data = job.input_data or {}
    audio_file = input_data.get("audio_file")
    style = input_data.get("style", "realistic")
    lyrics = input_data.get("lyrics")

    if lyrics and isinstance(lyrics, dict):
        duration = lyrics.get("duration", input_data.get("duration", 30))
    else:
        duration = input_data.get("duration", 30)

    if isinstance(lyrics, str):
        lines = [line for line in lyrics.split("\n") if line.strip()]
        lyrics = {
            "lyrics": [{"text": line, "start": 0.0, "end": 0.0} for line in lines],
            "lines": [{"text": line, "start": 0.0, "end": 0.0, "words": []} for line in lines],
            "full_text": lyrics,
            "duration": duration,
        }

    if not lyrics and audio_file:
        await broadcast_update(str(job.id), {
            "stage": "planning", "progress": 15,
            "status": "Extracting lyrics from audio...",
        })
        extractor = LyricsExtractor()
        try:
            audio_path = Path(settings.storage_path).resolve() / audio_file
            lyrics = await extractor.extract_from_audio(str(audio_path))
        except Exception as e:
            await broadcast_update(str(job.id), {
                "stage": "planning", "progress": 20,
                "status": f"Lyrics extraction failed: {e}. Using placeholder...",
            })
            lyrics = {
                "lyrics": [{"text": "Sample", "start": 0.0, "end": 3.0}],
                "lines": [{"text": "Sample", "start": 0.0, "end": 3.0, "words": []}],
                "full_text": "Sample",
                "duration": duration,
            }
        finally:
            await extractor.close()

    if not lyrics and not audio_file:
        raise RuntimeError(
            f"No lyrics available for job {job.id}. "
            "Please provide lyrics manually or ensure audio_file is uploaded."
        )
    if not lyrics:
        lyrics = {"lyrics": [], "lines": [], "full_text": "", "duration": duration}

    from sqlalchemy import update as sa_update

    await db.execute(
        sa_update(Job)
        .where(Job.id == job.id)
        .values(input_data={**(job.input_data or {}), "lyrics": lyrics})
    )
    await db.commit()
    result = await db.execute(select(Job).where(Job.id == job.id))
    job = result.scalar_one()

    planner = MusicVideoPlanner()
    try:
        result = await planner.plan_music_video(lyrics=lyrics, duration=duration, style=style)
    except Exception as e:
        await planner.close()
        raise RuntimeError(f"Scene planning failed: {e}")
    finally:
        await planner.close()
    scenes = result.get("scenes", [])

    await broadcast_update(str(job.id), {
        "progress": 50, "status": f"Creating {len(scenes)} scenes...",
    })

    existing = await db.execute(select(VideoScene).where(VideoScene.job_id == job.id))
    for scene in existing.scalars():
        await db.delete(scene)

    for i, scene_data in enumerate(scenes):
        scene = VideoScene(
            job_id=job.id,
            scene_number=i + 1,
            start_time=scene_data.get("start_time", 0),
            end_time=scene_data.get("end_time", 5),
            lyrics_segment=scene_data.get("lyrics_segment", ""),
            visual_description=scene_data.get("visual_description", ""),
            image_prompt=scene_data.get("image_prompt", ""),
            mood=scene_data.get("mood", "neutral"),
            camera_movement=scene_data.get("camera_movement", "static"),
            status="pending",
        )
        db.add(scene)

    job.stage = "planned"
    job.workflow_type = "scene_based"
    await db.commit()

    await broadcast_update(str(job.id), {
        "stage": "planned", "progress": 100,
        "status": "Planning complete. Review scenes and start generation.",
    })

    return {
        "status": "completed", "job_id": str(job.id),
        "stage": "planned", "scene_count": len(scenes),
    }


async def _stage_generating_images(db, job) -> dict:
    import app.services.media_generator as media_generator
    from app.database import VideoScene

    scenes_result = await db.execute(
        select(VideoScene)
        .where(VideoScene.job_id == job.id)
        .order_by(VideoScene.scene_number)
    )
    scenes = scenes_result.scalars().all()

    total = len(scenes)
    completed = 0

    for scene in scenes:
        if scene.reference_image_path:
            completed += 1
            continue

        await broadcast_update(str(job.id), {
            "stage": "generating_images",
            "progress": int((completed / total) * 100),
            "status": f"Generating image for scene {scene.scene_number}/{total}...",
            "scene_id": str(scene.id),
        })

        try:
            prompt = scene.image_prompt or scene.visual_description or scene.lyrics_segment or ""
            if not prompt:
                prompt = f"Scene {scene.scene_number}"

            image_path, media_id, provider_id = await media_generator.generate_image(
                db=db, job=job, prompt=prompt,
                scene_number=scene.scene_number,
                provider_id=job.image_provider_id,
            )

            scene.reference_image_path = image_path
            scene.status = "image_ready"
            scene.image_provider_id = provider_id

            try:
                from app.services.auto_import import _create_asset_from_file, _get_or_create_folder

                image_full_path = Path(settings.storage_path).resolve() / image_path
                if image_full_path.exists():
                    gen_folder = await _get_or_create_folder(
                        user_id=job.user_id, name="Generated Images",
                        parent_id=None, db=db,
                    )
                    await _create_asset_from_file(
                        user_id=job.user_id, folder_id=gen_folder.id,
                        name=f"Scene {scene.scene_number} - {str(job.id)[:8]}",
                        file_path=image_full_path, file_type="image",
                        source_job_id=job.id, db=db,
                        project_id=job.project_id,
                    )
            except Exception:
                logger.warning("Failed to create MediaAsset for image", exc_info=True)

            thumbnail_dir = (
                Path(settings.storage_path) / "output" / str(job.id)
                / f"scene_{scene.scene_number:03d}"
            )
            thumbnail_path = thumbnail_dir / "thumbnail.png"
            if thumbnail_path.exists():
                scene.thumbnail_path = str(
                    thumbnail_path.relative_to(settings.storage_path)
                )

        except Exception as e:
            scene.status = "failed"
            scene.error_message = str(e)

        await db.commit()
        completed += 1

    job.stage = "images_ready"
    await db.commit()

    await broadcast_update(str(job.id), {
        "stage": "images_ready", "progress": 100,
        "status": "Image generation complete.",
    })

    return {"status": "completed", "job_id": str(job.id), "stage": "images_ready"}


async def _stage_generating_videos(db, job) -> dict:
    import app.services.media_generator as media_generator
    from app.database import VideoScene

    scenes_result = await db.execute(
        select(VideoScene)
        .where(VideoScene.job_id == job.id)
        .order_by(VideoScene.scene_number)
    )
    scenes = scenes_result.scalars().all()

    total = len(scenes)
    completed = 0
    input_data = job.input_data or {}
    aspect_ratio = input_data.get("aspect_ratio", "16:9")

    for scene in scenes:
        if scene.generated_video_path:
            completed += 1
            continue

        await broadcast_update(str(job.id), {
            "stage": "generating_videos",
            "progress": int((completed / total) * 100),
            "status": f"Generating video for scene {scene.scene_number}/{total}...",
            "scene_id": str(scene.id),
        })

        try:
            duration = int(scene.end_time - scene.start_time)
            duration = max(2, min(duration, 5))
            prompt = scene.visual_description or scene.lyrics_segment or ""

            video_path, media_id, provider_id, actual_duration = (
                await media_generator.generate_video(
                    db=db, job=job, prompt=prompt,
                    scene_number=scene.scene_number,
                    reference_image_path=scene.reference_image_path,
                    provider_id=job.video_provider_id,
                    duration=duration, aspect_ratio=aspect_ratio,
                )
            )

            scene.generated_video_path = video_path
            scene.status = "video_ready"
            scene.video_provider_id = provider_id
            scene.duration = actual_duration

            # Create MediaAsset for the generated video
            try:
                from app.services.auto_import import _create_asset_from_file, _get_or_create_folder

                video_full_path = Path(settings.storage_path).resolve() / video_path
                if video_full_path.exists():
                    vid_folder = await _get_or_create_folder(
                        user_id=job.user_id, name="Generated Videos",
                        parent_id=None, db=db,
                    )
                    await _create_asset_from_file(
                        user_id=job.user_id, folder_id=vid_folder.id,
                        name=f"Scene {scene.scene_number} Video - {str(job.id)[:8]}",
                        file_path=video_full_path, file_type="video",
                        source_job_id=job.id, db=db,
                        project_id=job.project_id,
                    )
            except Exception:
                logger.warning("Failed to create MediaAsset for video", exc_info=True)

            if not scene.thumbnail_path:
                thumbnail_dir = (
                    Path(settings.storage_path) / "output" / str(job.id)
                    / f"scene_{scene.scene_number:03d}"
                )
                thumbnail_path = thumbnail_dir / "thumbnail.png"
                if thumbnail_path.exists():
                    scene.thumbnail_path = str(
                        thumbnail_path.relative_to(settings.storage_path)
                    )

        except Exception as e:
            scene.status = "failed"
            scene.error_message = str(e)

        await db.commit()
        completed += 1

    job.stage = "videos_ready"
    await db.commit()

    await broadcast_update(str(job.id), {
        "stage": "videos_ready", "progress": 100,
        "status": "Video generation complete.",
    })

    return {"status": "completed", "job_id": str(job.id), "stage": "videos_ready"}


async def _stage_rendering(db, job) -> dict:
    from app.database import VideoScene
    from app.services.video_processor import VideoProcessor

    await broadcast_update(str(job.id), {
        "stage": "rendering", "progress": 10,
        "status": "Preparing scene videos...",
    })

    scenes_result = await db.execute(
        select(VideoScene)
        .where(VideoScene.job_id == job.id, VideoScene.generated_video_path.isnot(None))
        .order_by(VideoScene.scene_number)
    )
    scenes = list(scenes_result.scalars().all())

    if not scenes:
        return {"status": "failed", "error": "No generated videos to render"}

    segment_paths = []
    storage_path = Path(settings.storage_path).resolve()
    for scene in scenes:
        full_path = storage_path / scene.generated_video_path
        if full_path.exists():
            segment_paths.append(str(full_path))

    await broadcast_update(str(job.id), {
        "progress": 30, "status": "Merging scene videos...",
    })

    output_dir = storage_path / "output" / str(job.id)
    merged_path = output_dir / "merged.mp4"

    if len(segment_paths) == 1:
        shutil.copy(segment_paths[0], merged_path)
    else:
        await VideoProcessor.merge_videos(segment_paths, str(merged_path))

    await broadcast_update(str(job.id), {
        "progress": 60, "status": "Adding audio...",
    })

    input_data = job.input_data or {}
    audio_file = input_data.get("audio_file")
    export_opts = job.export_options or {}
    final_path = output_dir / "final.mp4"

    if audio_file:
        audio_path = Path(settings.storage_path) / audio_file
        if audio_path.exists():
            audio_volume = export_opts.get("audio_volume", 1.0)
            await VideoProcessor.add_audio(
                str(merged_path), str(audio_path), str(final_path),
                audio_volume=audio_volume,
            )
        else:
            shutil.copy(str(merged_path), str(final_path))
    else:
        shutil.copy(str(merged_path), str(final_path))

    await broadcast_update(str(job.id), {
        "progress": 90, "status": "Generating preview...",
    })

    preview_path = output_dir / "preview.mp4"
    try:
        await VideoProcessor.generate_preview(
            str(final_path), str(preview_path),
            width=854, height=480, fps=15, quality=28,
        )
    except Exception:
        pass

    job.output_path = str(final_path.relative_to(storage_path))
    job.preview_path = str(preview_path.relative_to(storage_path))
    job.stage = "completed"
    job.status = "completed"

    # Create MediaAsset for the final video
    try:
        from app.services.auto_import import _create_asset_from_file, _get_or_create_folder

        if final_path.exists():
            final_folder = await _get_or_create_folder(
                user_id=job.user_id, name="Final Exports",
                parent_id=None, db=db,
            )
            await _create_asset_from_file(
                user_id=job.user_id, folder_id=final_folder.id,
                name=f"Final Export - {str(job.id)[:8]}",
                file_path=final_path, file_type="video",
                source_job_id=job.id, db=db,
                project_id=job.project_id,
            )
    except Exception:
        logger.warning("Failed to create MediaAsset for final video", exc_info=True)

    await db.commit()

    # Set completed_at timestamp in a separate session
    try:
        async with ctx.session_factory() as status_db:
            status_db_result = await status_db.execute(
                select(Job).where(Job.id == job.id)
            )
            status_job = status_db_result.scalar_one_or_none()
            if status_job and not status_job.completed_at:
                status_job.completed_at = datetime.utcnow()
                await status_db.commit()
    except Exception:
        pass

    await broadcast_update(str(job.id), {
        "stage": "completed", "progress": 100,
        "status": "Render complete!", "output_path": job.output_path,
    })

    return {
        "status": "completed", "job_id": str(job.id),
        "stage": "completed", "output_path": job.output_path,
    }


# ======================================================================
# Task 8: generate_scene_media
# ======================================================================


@celery_app.task(bind=True, time_limit=1800)
def generate_scene_media(
    self, job_id: str, scene_id: str, media_type: str = "video",
) -> dict:
    return ctx.run(_generate_scene_media(job_id, scene_id, media_type))


async def _generate_scene_media(
    job_id: str, scene_id: str, media_type: str = "video",
) -> dict:
    from app.database import VideoScene

    job_uuid = UUID(job_id)
    scene_uuid = UUID(scene_id)

    async with ctx.session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_uuid))
        job = result.scalar_one_or_none()
        if not job:
            return {"status": "failed", "error": "Job not found"}

        result = await db.execute(select(VideoScene).where(VideoScene.id == scene_uuid))
        scene = result.scalar_one_or_none()
        if not scene:
            return {"status": "failed", "error": "Scene not found"}

        await broadcast_update(job_id, {
            "status": f"Generating {media_type}...", "scene_id": scene_id,
        })

        try:
            import app.services.media_generator as media_generator

            if media_type == "image":
                prompt = (
                    scene.image_prompt or scene.visual_description
                    or scene.lyrics_segment or f"Scene {scene.scene_number}"
                )
                image_path, media_id, provider_id = await media_generator.generate_image(
                    db=db, job=job, prompt=prompt,
                    scene_number=scene.scene_number,
                    provider_id=job.image_provider_id,
                )
                scene.reference_image_path = image_path
                scene.status = "image_ready"
                scene.image_provider_id = provider_id

                await broadcast_update(job_id, {
                    "status": "Image generated", "scene_id": scene_id,
                    "reference_image_path": image_path,
                })

            elif media_type == "video":
                input_data = job.input_data or {}
                aspect_ratio = input_data.get("aspect_ratio", "16:9")
                duration = max(2, min(int(scene.end_time - scene.start_time), 5))
                prompt = scene.visual_description or scene.lyrics_segment or ""

                video_path, media_id, provider_id, actual_duration = (
                    await media_generator.generate_video(
                        db=db, job=job, prompt=prompt,
                        scene_number=scene.scene_number,
                        reference_image_path=scene.reference_image_path,
                        provider_id=job.video_provider_id,
                        duration=duration, aspect_ratio=aspect_ratio,
                    )
                )
                scene.generated_video_path = video_path
                scene.status = "video_ready"
                scene.video_provider_id = provider_id
                scene.duration = actual_duration

                await broadcast_update(job_id, {
                    "status": "Video generated", "scene_id": scene_id,
                    "generated_video_path": video_path,
                })
            else:
                return {"status": "failed", "error": f"Unknown media type: {media_type}"}

            await db.commit()
            return {
                "status": "completed", "job_id": job_id,
                "scene_id": scene_id, "media_type": media_type,
            }

        except Exception as e:
            scene.status = "failed"
            scene.error_message = str(e)
            await db.commit()

            await broadcast_update(job_id, {
                "status": f"Generation failed: {str(e)}",
                "scene_id": scene_id, "error": str(e),
            })
            return {"status": "failed", "error": str(e)}


# ======================================================================
# Task 9: export_scene_video
# ======================================================================


@celery_app.task(bind=True, time_limit=1800)
def export_scene_video(self, job_id: str, options: dict | None = None) -> dict:
    return ctx.run(_export_scene_video(job_id, options or {}))


async def _export_scene_video(job_id: str, options: dict) -> dict:
    from app.database import VideoScene
    from app.services.video_processor import VideoProcessor

    job_uuid = UUID(job_id)

    async with ctx.session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_uuid))
        job = result.scalar_one_or_none()
        if not job:
            return {"status": "failed", "error": "Job not found"}

        await broadcast_update(job_id, {
            "stage": "rendering", "status": "Preparing export...",
        })

        scenes_result = await db.execute(
            select(VideoScene)
            .where(VideoScene.job_id == job.id, VideoScene.generated_video_path.isnot(None))
            .order_by(VideoScene.scene_number)
        )
        scenes = list(scenes_result.scalars().all())

        if not scenes:
            return {"status": "failed", "error": "No generated videos to export"}

        segment_paths = []
        storage_path = Path(settings.storage_path).resolve()
        for scene in scenes:
            full_path = storage_path / scene.generated_video_path
            if full_path.exists():
                segment_paths.append(str(full_path))

        output_dir = storage_path / "output" / job_id
        merged_path = output_dir / "merged.mp4"

        await broadcast_update(job_id, {"status": "Merging videos..."})
        if len(segment_paths) == 1:
            shutil.copy(segment_paths[0], merged_path)
        else:
            await VideoProcessor.merge_videos(segment_paths, str(merged_path))

        audio_volume = options.get("audio_volume", 1.0)
        background_music_volume = options.get("background_music_volume", 0.0)
        audio_file = options.get("audio_file")
        music_file = options.get("background_music")
        final_path = output_dir / "final.mp4"

        if audio_file or music_file:
            audio_inputs = []
            if audio_file:
                audio_path = storage_path / audio_file
                if audio_path.exists():
                    audio_inputs.append(str(audio_path))
            if music_file:
                music_path = storage_path / music_file
                if music_path.exists():
                    audio_inputs.append(str(music_path))

            if audio_inputs:
                await broadcast_update(job_id, {"status": "Mixing audio..."})
                if len(audio_inputs) == 1:
                    await VideoProcessor.add_audio(
                        str(merged_path), audio_inputs[0], str(final_path),
                        audio_volume=audio_volume,
                    )
                else:
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                        combined_audio = tmp.name
                    if len(audio_inputs) == 2:
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", audio_inputs[0], "-i", audio_inputs[1],
                            "-filter_complex",
                            (
                                f"[0:a]volume={audio_volume}[a];"
                                f"[1:a]volume={background_music_volume}[b];"
                                f"[a][b]amix=inputs=2:duration=longest[a]"
                            ),
                            "-map", "[a]", combined_audio,
                        ]
                        subprocess.run(cmd, check=True, capture_output=True)

                    await VideoProcessor.add_audio(
                        str(merged_path), combined_audio, str(final_path),
                        audio_volume=1.0,
                    )
                    Path(combined_audio).unlink(missing_ok=True)
        else:
            shutil.copy(str(merged_path), str(final_path))

        await broadcast_update(job_id, {"status": "Generating preview..."})
        preview_path = output_dir / "preview.mp4"
        try:
            await VideoProcessor.generate_preview(
                str(final_path), str(preview_path),
                width=854, height=480, fps=15, quality=28,
            )
        except Exception:
            pass

        job.output_path = str(final_path.relative_to(storage_path))
        job.preview_path = str(preview_path.relative_to(storage_path))
        job.export_options = options
        job.stage = "completed"
        job.status = "completed"

        # Create MediaAsset for the final video
        try:
            from app.services.auto_import import _create_asset_from_file, _get_or_create_folder

            if final_path.exists():
                final_folder = await _get_or_create_folder(
                    user_id=job.user_id, name="Final Exports",
                    parent_id=None, db=db,
                )
                await _create_asset_from_file(
                    user_id=job.user_id, folder_id=final_folder.id,
                    name=f"Final Export - {str(job.id)[:8]}",
                    file_path=final_path, file_type="video",
                    source_job_id=job.id, db=db,
                    project_id=job.project_id,
                )
        except Exception:
            logger.warning("Failed to create MediaAsset for final video", exc_info=True)

        await db.commit()

        # update_job_status opens its own session; we've already committed
        # the output_path above, so we only need the broadcast side-effect.
        try:
            async with ctx.session_factory() as status_db:
                status_db_result = await status_db.execute(
                    select(Job).where(Job.id == job.id)
                )
                status_job = status_db_result.scalar_one_or_none()
                if status_job and not status_job.completed_at:
                    status_job.completed_at = datetime.utcnow()
                    await status_db.commit()
        except Exception:
            pass

        await broadcast_update(job_id, {
            "stage": "completed", "status": "Export complete!",
            "output_path": job.output_path, "preview_path": job.preview_path,
        })

        return {
            "status": "completed", "job_id": job_id,
            "output_path": job.output_path, "preview_path": job.preview_path,
        }
