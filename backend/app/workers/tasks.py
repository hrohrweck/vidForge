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
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.websocket import manager as ws_manager
from app.config import get_settings
from app.database import ErrorEvent, ErrorOrigin, ErrorSeverity, Job, Message, Provider, Template
from app.services.budget_tracker import BudgetTracker
from app.services.error_capture import log_user_error
from app.services.job_router import JobRouter
from app.services.worker_registry import WorkerRegistry
from app.storage import get_storage_backend
from app.workers.celery_app import celery_app
from app.workers.context import ctx

logger = logging.getLogger(__name__)


settings = get_settings()

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
    await broadcast_update(job_id, {"type": "progress", "progress": progress, "message": message})


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

    if status == "completed":
        await _post_completion_message(job_id)


async def _post_completion_message(job_id: UUID, db: AsyncSession | None = None) -> None:
    """If the job was triggered from chat, post the result as an assistant message."""
    if db is None:
        async with ctx.session_factory() as db:
            return await _post_completion_message(job_id, db=db)

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job or not job.chat_conversation_id:
        return

    dup_result = await db.execute(
        select(Message).where(
            Message.conversation_id == job.chat_conversation_id,
            Message.job_id == job.id,
        )
    )
    if dup_result.scalar_one_or_none():
        return

    media_path = job.output_path or job.preview_path
    if not media_path:
        return

    ext = Path(media_path).suffix.lower()
    kind_map = {
        ".mp4": "video",
        ".webm": "video",
        ".mov": "video",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".webp": "image",
        ".gif": "image",
        ".mp3": "audio",
        ".wav": "audio",
        ".ogg": "audio",
        ".m4a": "audio",
    }
    kind = kind_map.get(ext, "video")
    mime_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
    }
    mime_type = mime_map.get(ext, "application/octet-stream")

    storage = get_storage_backend()
    url = await storage.get_url(media_path)

    message = Message(
        id=uuid4(),
        conversation_id=job.chat_conversation_id,
        role="assistant",
        content="Here is the result:",
        attachments=[{"kind": kind, "url": url, "mime_type": mime_type}],
        job_id=job.id,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await ws_manager.broadcast_chat_message(str(job.chat_conversation_id), str(message.id))


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
# Provider concurrency semaphore (async Redis)
# ======================================================================


class ProviderSemaphore:
    """Redis-based semaphore for limiting concurrent jobs per provider.

    Uses the shared ``ctx.redis`` (async) client — no per-instance
    connection is created.  Generic across all provider types.
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


async def _resolve_provider_for_job(db, job: Job, workflow: dict, preference: str) -> tuple:
    router = JobRouter(db)

    if job.provider_id:
        provider = await router.get_provider_record(job.provider_id)
        if not provider:
            raise ValueError(f"Assigned provider {job.provider_id} no longer exists")
        if not provider.is_active:
            raise ValueError(f"Assigned provider '{provider.name}' is inactive")

        provider_instance = await router.get_provider_instance(provider.id)
        estimated_cost = Decimal(str(await provider_instance.estimate_cost(workflow)))

        return provider, provider_instance, estimated_cost, router, "Assigned provider"

    provider, provider_instance, reason = await router.select_provider(
        preference=preference,
        workflow=workflow,
    )
    estimated_cost = Decimal(str(await provider_instance.estimate_cost(workflow)))
    return provider, provider_instance, estimated_cost, router, reason





# ======================================================================
# Task 1: process_video_job
# ======================================================================


@celery_app.task(bind=True, time_limit=TASK_TIME_LIMIT)
def process_video_job(self, job_id: str, provider_preference: str = "auto") -> dict:
    return ctx.run(_process_video_job(job_id, provider_preference))


def _map_exception_to_friendly_message(exc: Exception) -> str:
    """Map common exceptions to user-friendly messages."""
    exc_msg = str(exc).lower()

    if "overloaded" in exc_msg or "capacity" in exc_msg or "queue is full" in exc_msg:
        return "AI service is busy, please try again later"
    if "rate limit" in exc_msg or "429" in exc_msg or "too many requests" in exc_msg:
        return "Too many requests, please try again later"
    if isinstance(exc, ConnectionError) or "connection" in exc_msg:
        return "Connection failed, please check your network"
    if isinstance(exc, TimeoutError) or "timeout" in exc_msg or "timed out" in exc_msg:
        return "Request timed out, please try again later"
    if "provider" in exc_msg or "generation service" in exc_msg:
        return "Video generation service error, please try again"
    return "An error occurred, please try again"


def _build_error_details(exc: Exception, **extra_context) -> dict:
    """Build a details dict with technical info for admin viewing."""
    import traceback

    details = {
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
    }
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    details["stack_trace"] = "".join(tb_lines[-5:])
    details.update(extra_context)
    return details


async def _process_video_job(job_id: str, provider_preference: str = "auto") -> dict:
    job_uuid = UUID(job_id)

    await update_job_status(job_uuid, "queued", 0)

    async with ctx.session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_uuid))
        job = result.scalar_one_or_none()
        print(f"DEBUG: db={type(db)}, result={type(result)}, job={type(job)}")
        if not job:
            raise ValueError(f"Job {job_id} not found")

        template_name = await get_template_name(db, job.template_id)
        preference = job.provider_preference or provider_preference

        if not job.provider_preference:
            job.provider_preference = preference
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
                job_uuid,
                "processing",
                0,
                provider_id=provider_record.id,
                estimated_cost=estimated_cost,
            )

            started_at = datetime.utcnow()

            # Acquire capacity semaphore for providers that need it
            max_concurrent = provider_record.config.get("max_concurrent_jobs", 0)
            if max_concurrent > 0:
                semaphore = ProviderSemaphore(
                    key=f"provider:processing:{provider_record.id}",
                    max_concurrent=max_concurrent,
                )
                acquired = await semaphore.acquire(job_id)
                if not acquired:
                    await update_job_status(
                        job_uuid,
                        "failed",
                        0,
                        error_message="Provider queue is full. Job will be retried.",
                    )
                    return {"status": "failed", "error": "Queue full", "job_id": job_id}

            from sqlalchemy import delete as sa_delete

            from app.database import VideoScene
            from app.workers.dispatcher import dispatch_stage

            # Clear any stale scenes and mark as scene-based
            job.workflow_type = "scene_based"
            await db.execute(
                sa_delete(VideoScene).where(VideoScene.job_id == job_uuid)
            )
            await db.commit()

            # Run pipeline stages sequentially: planning → images → videos → render
            for stage in (
                "planning",
                "generating_images",
                "generating_videos",
                "rendering",
            ):
                result = await dispatch_stage(job_id, stage)
                if result.get("status") == "failed":
                    return {
                        "status": "failed",
                        "error": result.get(
                            "error_message", f"Pipeline stage '{stage}' failed"
                        ),
                        "job_id": job_id,
                        "stage": stage,
                    }

            # Reload job to pick up output_path / preview_path set by
            # the rendering stage (which ran in a separate db session).
            await db.refresh(job)
            relative_video = job.output_path
            relative_preview = job.preview_path

            # --- Record cost for all provider types -----------------------
            actual_cost = _as_decimal(estimated_cost)
            duration_seconds = max(1, int((datetime.utcnow() - started_at).total_seconds()))
            budget_tracker = BudgetTracker(db)
            await budget_tracker.record_spend(
                provider_record.id,
                job_uuid,
                actual_cost,
                duration_seconds=duration_seconds,
                gpu_type=provider_record.config.get("gpu_type"),
            )

            await update_job_status(
                job_uuid,
                "completed",
                100,
                output_path=relative_video,
                preview_path=relative_preview,
                actual_cost=actual_cost,
            )
            return {"status": "completed", "job_id": job_id}

        except Exception as exc:
            error_message = str(exc)
            await update_job_status(job_uuid, "failed", 0, error_message=error_message)

            # Capture error for notification system
            try:
                friendly_message = _map_exception_to_friendly_message(exc)
                details = _build_error_details(
                    exc,
                    job_id=job_id,
                    template_name=template_name,
                    provider_type=provider_record.provider_type if provider_record else None,
                )
                await log_user_error(
                    db,
                    user_id=job.user_id,
                    severity=ErrorSeverity.ERROR,
                    origin=ErrorOrigin.VIDEO_GENERATION,
                    message=friendly_message,
                    details=details,
                    source_id=job.id,
                    source_type="job",
                )
            except Exception as capture_exc:
                logger.warning(
                    "Failed to capture error for job %s: %s",
                    job_id,
                    capture_exc,
                )

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
            select(Provider).where(Provider.provider_type == "comfyui_direct", Provider.is_active)
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


@celery_app.task(
    bind=True,
    time_limit=TASK_TIME_LIMIT,
    max_retries=3,
    default_retry_delay=30,
)
def process_scene_video_job(self, job_id: str, stage: str = "planning") -> dict:
    """Run a pipeline stage via the plugin dispatcher."""
    from app.workers.dispatcher import dispatch_stage

    return ctx.run(dispatch_stage(job_id, stage))


# ======================================================================
# Scene-based pipeline stages
# ======================================================================


@celery_app.task(bind=True, time_limit=1800)
def generate_scene_media(
    self,
    job_id: str,
    scene_id: str,
    media_type: str = "video",
) -> dict:
    """Re-render a single scene via the plugin dispatcher."""
    from app.workers.dispatcher import dispatch_scene_rerender

    return ctx.run(dispatch_scene_rerender(job_id, scene_id, media_type))


# ======================================================================
# Task 9: export_scene_video
# ======================================================================


@celery_app.task(bind=True, time_limit=1800)
def export_scene_video(self, job_id: str, options: dict | None = None) -> dict:
    return ctx.run(_export_scene_video(job_id, options or {}))


async def _export_scene_video(job_id: str, options: dict) -> dict:
    """Export final video using the plugin dispatcher's render pipeline.

    This delegates to ``dispatch_stage('rendering')`` which uses the
    plugin's ``render()`` method — including clip stretching, audio
    mixing, preview generation, and MediaAsset creation.
    """
    from app.workers.dispatcher import dispatch_stage

    # Apply export options to the job first
    job_uuid = UUID(job_id)
    async with ctx.session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_uuid))
        job = result.scalar_one_or_none()
        if not job:
            return {"status": "failed", "error": "Job not found"}
        job.export_options = options
        await db.commit()

    return await dispatch_stage(job_id, "rendering")


# ======================================================================
# Task 10: train_avatar_lora
# ======================================================================


@celery_app.task(bind=True, time_limit=3600)
def train_avatar_lora(self, avatar_id: str) -> dict:
    return ctx.run(_train_avatar_lora(avatar_id))


async def _train_avatar_lora(avatar_id: str) -> dict:
    import shutil

    from app.database import Avatar

    async with ctx.session_factory() as db:
        avatar = await db.get(Avatar, UUID(avatar_id))
        if not avatar:
            return {"status": "failed", "error": "Avatar not found"}

        avatar.lora_training_status = "training"
        await db.commit()

        try:
            # Collect training image paths
            from sqlalchemy import select as sa_select
            from sqlalchemy.orm import selectinload

            result = await db.execute(
                sa_select(Avatar)
                .options(selectinload(Avatar.images))
                .where(Avatar.id == UUID(avatar_id))
            )
            avatar_with_images = result.scalar_one()
            images = [img for img in avatar_with_images.images if img.storage_path]
            if len(images) < 3:
                logger.warning(
                    "Avatar %s has only %d images; LoRA training unavailable (need ≥3)",
                    avatar_id,
                    len(images),
                )
                avatar.lora_training_status = "unavailable"
                avatar.lora_model_path = None
                await db.commit()
                return {"status": "completed", "avatar_id": avatar_id}

            # Generate caption
            caption = f"{avatar.name}, {avatar.gender}"
            if avatar.bio:
                caption += f", {avatar.bio}"

            # Create training directory
            train_dir = Path(settings.storage_path) / "loras" / str(avatar.id)
            train_dir.mkdir(parents=True, exist_ok=True)

            # Copy images and write captions
            for i, img in enumerate(images):
                src = Path(settings.storage_path) / img.storage_path
                if src.exists():
                    dst = train_dir / f"image_{i}{src.suffix}"
                    shutil.copy2(src, dst)
                    (train_dir / f"image_{i}.txt").write_text(caption)

            # Placeholder: actual LoRA training would happen here
            import asyncio

            await asyncio.sleep(2)

            # Mark as trained
            avatar.lora_model_path = str(train_dir / "avatar_lora.safetensors")
            avatar.lora_training_status = "trained"
            await db.commit()

        except Exception:
            avatar.lora_training_status = "failed"
            await db.commit()
            raise

    return {"status": "completed", "avatar_id": avatar_id}


@celery_app.task(bind=True, time_limit=300)
def cleanup_orphaned_avatars(self):
    return ctx.run(_cleanup_orphaned_avatars())


async def _cleanup_orphaned_avatars():
    from datetime import timedelta

    from app.database import Avatar, JobAvatar

    async with ctx.session_factory() as db:
        cutoff = datetime.utcnow() - timedelta(days=30)

        result = await db.execute(
            select(Avatar).where(
                Avatar.deleted_at.is_not(None),
                Avatar.deleted_at < cutoff,
            )
        )
        candidates = result.scalars().all()

        cleaned = 0
        for avatar in candidates:
            ref_result = await db.execute(select(JobAvatar).where(JobAvatar.avatar_id == avatar.id))
            if ref_result.first() is None:
                for img in avatar.images:
                    img_path = Path(settings.storage_path) / img.storage_path
                    if img_path.exists():
                        img_path.unlink()
                await db.delete(avatar)
                cleaned += 1

        await db.commit()
        logger.info("Cleaned up %s orphaned avatars", cleaned)
        return {"status": "completed", "cleaned": cleaned}


# ======================================================================
# Task 11: generate_avatar_poses
# ======================================================================


@celery_app.task(bind=True, time_limit=600)
def generate_avatar_poses_task(self, avatar_id: str) -> dict:
    return ctx.run(_generate_avatar_poses(avatar_id))


async def _generate_avatar_poses(avatar_id: str) -> dict:
    from types import SimpleNamespace

    from app.database import Avatar, AvatarImage
    from app.services.media_generator import generate_image

    lock_key = f"avatar:poses:generating:{avatar_id}"

    # Acquire Redis lock — only one generation per avatar at a time
    acquired = await ctx.redis.set(lock_key, "1", nx=True, ex=600)
    if not acquired:
        return {"status": "skipped", "reason": "already generating"}

    try:
        async with ctx.session_factory() as db:
            avatar = await db.get(Avatar, UUID(avatar_id))
            if not avatar:
                return {"status": "failed", "error": "Avatar not found"}
            if not avatar.primary_image:
                return {"status": "failed", "error": "No primary image set"}

            primary_path = str(Path(settings.storage_path) / avatar.primary_image.storage_path)

            # Mock job for generate_image — it only needs id and user_id
            mock_job = SimpleNamespace(
                id=UUID(avatar_id),
                user_id=avatar.user_id,
                provider_id=None,
            )

            base_prompt = f"{avatar.name}, {avatar.gender}" + (
                f", {avatar.bio}" if avatar.bio else ""
            )
            poses = [
                (f"front portrait of {base_prompt}"),
                (f"3/4 profile view of {base_prompt}"),
                (f"full body shot of {base_prompt}, standing pose"),
            ]

            max_order = max((img.sort_order for img in avatar.images), default=0)

            for i, prompt in enumerate(poses):
                try:
                    path, _model, _pid = await generate_image(
                        db=db,
                        job=mock_job,  # type: ignore[arg-type]
                        prompt=prompt,
                        scene_number=i,
                        reference_image_path=primary_path,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to generate pose %d for avatar %s: %s",
                        i,
                        avatar_id,
                        exc,
                    )
                    continue

                img = AvatarImage(
                    avatar_id=avatar.id,
                    storage_path=path,
                    is_primary=False,
                    sort_order=max_order + i + 1,
                )
                db.add(img)

            await db.commit()

        return {"status": "completed", "avatar_id": avatar_id}
    finally:
        await ctx.redis.delete(lock_key)


# ======================================================================
# Task 12: sync_provider_models
# ======================================================================


@celery_app.task(bind=True, time_limit=600)
def sync_provider_models(self, provider_type: str) -> dict:
    """Sync ModelConfig rows for all active providers of the given type.

    Discovers available models (via API for remote providers, static
    list for local providers), upserts them, and marks any previously
    known but now-missing models as deprecated.

    Called by the Celery beat scheduler once per day per provider type
    at staggered times to avoid simultaneous API calls.
    """
    return ctx.run(_sync_provider_models(provider_type))


async def _sync_provider_models(provider_type: str) -> dict:
    from datetime import datetime

    from app.database import Provider
    from app.services.model_config_service import ModelConfigService

    async with ctx.session_factory() as db:
        result = await db.execute(
            select(Provider).where(
                Provider.provider_type == provider_type,
                Provider.is_active == True,  # noqa: E712
            )
        )
        providers = result.scalars().all()

        if not providers:
            logger.info("[Sync] No active providers found for type '%s'", provider_type)
            return {"provider_type": provider_type, "synced": 0, "deprecated": 0}

        total_synced = 0
        total_deprecated = 0

        for provider in providers:
            discovered = await _discover_models_via_registry(provider)

            service = ModelConfigService()
            discovered_ids = {m["model_id"] for m in discovered}

            for model_data in discovered:
                model_id = model_data.get("model_id") or model_data.get("id")
                if not model_id:
                    continue
                model_data.setdefault("last_synced_at", datetime.utcnow())
                await service.upsert(db, provider.id, model_id, model_data)
                total_synced += 1

            # Mark models not in discovered set as deprecated
            all_configs = await service.list_by_provider(db, provider.id, active_only=False)
            for config in all_configs:
                if config.model_id not in discovered_ids and not config.is_deprecated:
                    config.is_deprecated = True
                    config.is_active = False
                    total_deprecated += 1

        await db.commit()

    logger.info(
        "[Sync] provider_type=%s synced=%d deprecated=%d",
        provider_type,
        total_synced,
        total_deprecated,
    )
    return {
        "provider_type": provider_type,
        "synced": total_synced,
        "deprecated": total_deprecated,
    }


async def _discover_models_via_registry(provider) -> list[dict]:
    """Use the provider registry to discover models for any provider type.

    Creates a provider instance via the registry, checks if the provider
    supports model sync, and delegates to its sync_models() method.
    """
    from typing import Any, cast

    from app.services.providers import registry

    instance: Any = None
    try:
        instance = await registry.create(
            provider.provider_type, provider.id, provider.config
        )
        capabilities = cast(Any, instance).get_capabilities()

        if not capabilities.supports_model_sync:
            logger.debug(
                "[Sync] Provider %s (%s) does not support model sync",
                provider.name,
                provider.provider_type,
            )
            return []

        discovered = await cast(Any, instance).sync_models()
        if not discovered:
            logger.info(
                "[Sync] No models discovered for provider %s",
                provider.name,
            )
            return []

        return discovered
    except NotImplementedError:
        logger.debug(
            "[Sync] Provider %s (%s) does not implement sync_models",
            provider.name,
            provider.provider_type,
        )
        return []
    except Exception:
        logger.warning(
            "[Sync] Failed to discover models for provider %s",
            provider.name,
            exc_info=True,
        )
        return []
    finally:
        if instance is not None and hasattr(instance, "shutdown"):
            try:
                await cast(Any, instance).shutdown()
            except Exception:
                pass


# ======================================================================
# Task: generate_quick_media (job-less quick-create)
# ======================================================================


@celery_app.task(bind=True, time_limit=600, max_retries=4, default_retry_delay=10)
def generate_quick_media(
    self,
    user_id: str,
    model_id: str,
    prompt: str,
    aspect_ratio: str = "1:1",
    duration: int = 5,
    negative_prompt: str | None = None,
    seed: int | None = None,
    image_path: str | None = None,
    title: str | None = None,
) -> dict:
    """Generate a single image or video without a full job pipeline.

    Dispatches to :func:`generate_image` or :func:`generate_video` based
    on the model's configured modality.  Recoverable errors are retried
    with exponential back-off (10 s, 20 s, 40 s, 80 s).  Successful
    outputs are auto-imported into the user's media library.
    """
    return ctx.run(
        _generate_quick_media(
            self,
            user_id,
            model_id,
            prompt,
            aspect_ratio,
            duration,
            negative_prompt,
            seed,
            image_path,
            title=title,
        )
    )


async def _generate_quick_media(
    self,
    user_id: str,
    model_id: str,
    prompt: str,
    aspect_ratio: str,
    duration: int,
    negative_prompt: str | None,
    seed: int | None,
    image_path: str | None = None,
    title: str | None = None,
) -> dict:
    import uuid as _uuid
    from datetime import datetime as _datetime

    from app.database import ModelConfig, Provider
    from app.models.media import MediaAsset, SourceType
    from app.services.media_generator import generate_image, generate_video

    user_uuid = UUID(user_id)

    async with ctx.session_factory() as db:
        try:
            # ------------------------------------------------------------------
            # 1. Resolve model config
            # ------------------------------------------------------------------
            result = await db.execute(
                select(ModelConfig).where(
                    ModelConfig.model_id == model_id,
                    ModelConfig.is_active == True,  # noqa: E712
                )
            )
            config = result.scalars().first()
            if not config:
                raise ValueError(f"Unknown or inactive model: {model_id}")

            # ------------------------------------------------------------------
            # 2. Resolve provider
            # ------------------------------------------------------------------
            provider_result = await db.execute(
                select(Provider).where(
                    Provider.id == config.provider_id,
                    Provider.is_active == True,  # noqa: E712
                )
            )
            provider = provider_result.scalar_one_or_none()
            if not provider:
                raise ValueError(
                    f"Provider {config.provider_id} for model {model_id} is not available"
                )

            # ------------------------------------------------------------------
            # 3. Build a lightweight mock-job so we can reuse
            #    generate_image / generate_video
            # ------------------------------------------------------------------
            quick_job_id = _uuid.uuid4()

            class _QuickJob:
                id: UUID = quick_job_id
                image_provider_id: UUID | None = None
                video_provider_id: UUID | None = None

                def __init__(self, uid: UUID) -> None:
                    self.user_id: UUID = uid

            quick_job = _QuickJob(user_uuid)
            # Set the relevant provider id on the mock job
            if config.modality == "image":
                quick_job.image_provider_id = provider.id
            elif config.modality == "video":
                quick_job.video_provider_id = provider.id

            # ------------------------------------------------------------------
            # 4. Generate
            # ------------------------------------------------------------------
            if config.modality == "image":
                path, model_used, prov_id = await generate_image(
                    db=db,
                    job=quick_job,  # type: ignore[arg-type]
                    prompt=prompt,
                    scene_number=0,
                    provider_id=provider.id,
                    model_preference=model_id,
                    aspect_ratio=aspect_ratio,
                    reference_image_path=image_path,
                    title=title,
                )
                content_type = "image/png"

            elif config.modality == "video":
                path, model_used, prov_id, dur_out, _warning = await generate_video(
                    db=db,
                    job=quick_job,  # type: ignore[arg-type]
                    prompt=prompt,
                    scene_number=0,
                    provider_id=provider.id,
                    model_preference=model_id,
                    duration=duration,
                    aspect_ratio=aspect_ratio,
                    reference_image_path=image_path,
                    title=title,
                )
                content_type = "video/mp4"
            else:
                raise ValueError(f"Unsupported modality '{config.modality}' for model {model_id}")

            # ------------------------------------------------------------------
            # 5. Auto-import to media library
            # ------------------------------------------------------------------
            full_path = Path(settings.storage_path) / path
            if not full_path.exists():
                raise RuntimeError(f"Generated file not found at: {full_path}")

            asset_name = (
                title or prompt[:50] or f"{model_id}_{_datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            asset = MediaAsset(
                user_id=user_uuid,
                name=asset_name,
                file_path="",
                file_type="image" if config.modality == "image" else "video",
                mime_type=content_type,
                size_bytes=0,
                source_type=SourceType.GENERATED,
            )
            db.add(asset)
            await db.flush()

            from app.services.media_path import asset_path

            permanent_path = asset_path(user_uuid, asset.id, full_path.name)
            permanent_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(full_path, permanent_path)

            if not permanent_path.exists():
                raise RuntimeError(
                    f"Failed to copy generated file to permanent location: {permanent_path}"
                )

            asset.file_path = str(permanent_path.resolve())
            asset.size_bytes = full_path.stat().st_size
            await db.commit()

            # ------------------------------------------------------------------
            # 6. Record cost on the asset
            # ------------------------------------------------------------------
            from decimal import Decimal

            if config and config.cost_config:
                cc = config.cost_config
                if config.modality == "image":
                    cost = Decimal(str(cc.get("credits_per_image", cc.get("compute_points", 0))))
                    asset.cost = cost
                elif config.modality == "video":
                    cost_per_sec = Decimal(
                        str(
                            cc.get(
                                "credits_per_second",
                                cc.get("compute_points_per_second", 0),
                            )
                        )
                    )
                    asset.cost = cost_per_sec * duration
                await db.commit()
                logger.info("Quick media generation cost: %s", asset.cost)

            # ------------------------------------------------------------------
            # 7. Clean up the temp job output dir
            # ------------------------------------------------------------------
            job_output_dir = Path(settings.storage_path) / "output" / str(quick_job_id)
            if job_output_dir.exists():
                try:
                    shutil.rmtree(job_output_dir)
                except OSError:
                    logger.debug(
                        "Could not remove temp job output dir: %s",
                        job_output_dir,
                    )

            return {
                "status": "completed",
                "path": path,
                "model": model_used,
                "asset_id": str(asset.id),
            }

        except Exception as exc:
            # --- recoverable vs non-recoverable classification ---
            if _is_quick_recoverable(exc):
                if self.request.retries < self.max_retries:
                    countdown = 10 * (2**self.request.retries)
                    logger.warning(
                        "[quick_create] Attempt %d/%d failed for model=%s "
                        "(recoverable): %s — retrying in %ds",
                        self.request.retries + 1,
                        self.max_retries + 1,
                        model_id,
                        exc,
                        countdown,
                    )
                    raise self.retry(exc=exc, countdown=countdown)
                raise
            raise


# ------------------------------------------------------------------
# Recoverable-error classification (shared with PluginBase markers
# plus a few extras relevant to quick-create).
# ------------------------------------------------------------------

_QUICK_RECOVERABLE_MARKERS = (
    "overloaded",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
    "connection refused",
    "capacity",
    "queue is full",
    "queue full",
    "server error",
    "temporary",
    "too many requests",
    "try again",
    "busy",
)


def _is_quick_recoverable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _QUICK_RECOVERABLE_MARKERS)


# ======================================================================
# Task: cleanup_old_notifications
# ======================================================================


@celery_app.task
def cleanup_old_notifications() -> dict:
    """Delete error_events older than the configured retention period."""
    return ctx.run(_cleanup_old_notifications())


async def _cleanup_old_notifications() -> dict:
    from datetime import timedelta

    from sqlalchemy import delete as sa_delete

    from app.services.app_settings import get_setting

    async with ctx.session_factory() as db:
        retention_days = await get_setting(db, "notifications.retention_days", 30)
        try:
            retention_days = int(retention_days)
        except (TypeError, ValueError):
            retention_days = 30

        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        result = await db.execute(sa_delete(ErrorEvent).where(ErrorEvent.created_at < cutoff))
        await db.commit()

        deleted = result.rowcount
        if deleted > 0:
            logger.info(
                "[Cleanup] Deleted %d error_events older than %d days",
                deleted,
                retention_days,
            )

    return {"deleted": deleted}


# ======================================================================
# Task 14: sync_all_provider_models (dynamic beat schedule)
# ======================================================================


@celery_app.task(bind=True, time_limit=600)
def sync_all_provider_models(self) -> dict:
    """Query all active providers from DB and dispatch sync_provider_models for each type.

    Replaces the previous approach of hardcoding per-provider beat schedule
    entries. This single periodic task dynamically discovers which provider
    types have active providers and dispatches individual sync tasks.
    """
    return ctx.run(_sync_all_provider_models())


async def _sync_all_provider_models() -> dict:
    from app.database import Provider

    async with ctx.session_factory() as db:
        result = await db.execute(
            select(Provider.provider_type)
            .distinct()
            .where(Provider.is_active == True)  # noqa: E712
        )
        types = [row[0] for row in result.all()]

    if not types:
        logger.info("[SyncAll] No active providers found")
        return {"dispatched": 0, "types": []}

    for provider_type in types:
        sync_provider_models.delay(provider_type)

    logger.info("[SyncAll] Dispatched sync for %d provider types: %s", len(types), types)
    return {"dispatched": len(types), "types": types}
