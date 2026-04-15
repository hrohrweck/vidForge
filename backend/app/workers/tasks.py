import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import UUID

import redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Job, Provider, Template
from app.services.budget_tracker import BudgetTracker
from app.services.job_router import JobRouter
from app.services.video_generator import process_job_video
from app.services.worker_registry import WorkerRegistry
from app.workers.celery_app import celery_app

settings = get_settings()

COMFYUI_SEMAPHORE_KEY = "comfyui:processing"
COMFYUI_MAX_CONCURRENT = getattr(settings, "comfyui_max_concurrent", 1)
TASK_TIME_LIMIT = getattr(settings, "task_time_limit", 172800)


class ComfyUISemaphore:
    """Redis-based semaphore for limiting concurrent local ComfyUI jobs."""

    def __init__(self, key: str, max_concurrent: int):
        self.redis_client = redis.from_url(settings.redis_url)
        self.key = key
        self.max_concurrent = max_concurrent
        self._acquired = False
        self._job_id = None

    async def acquire(self, job_id: str, timeout: Optional[float] = None) -> bool:
        current = int(self.redis_client.get(self.key) or 0)
        if current < self.max_concurrent:
            self.redis_client.incr(self.key)
            self._acquired = True
            self._job_id = job_id
            return True
        return False

    async def release(self):
        if self._acquired:
            current = int(self.redis_client.get(self.key) or 0)
            if current > 0:
                self.redis_client.decr(self.key)
            self._acquired = False
            self._job_id = None


def get_db_session_factory():
    engine = create_async_engine(settings.database_url, echo=settings.debug)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url)


def broadcast_update(job_id: str, message: dict) -> None:
    r = get_redis()
    r.publish(f"job:{job_id}", json.dumps(message))


async def get_template_name(template_id: UUID | None) -> str:
    """Get template name from database by ID."""
    if template_id is None:
        return "prompt_to_video"
    async_session_maker = get_db_session_factory()
    async with async_session_maker() as db:
        result = await db.execute(select(Template).where(Template.id == template_id))
        template = result.scalar_one_or_none()
        if template:
            return template.name
    return "prompt_to_video"


def progress_callback_wrapper(job_id: str, progress: int, message: str) -> None:
    """Broadcast progress updates to subscribers."""
    try:
        broadcast_update(job_id, {"type": "progress", "progress": progress, "message": message})
    except Exception:
        pass


async def async_progress_callback(job_id: str, progress: int, message: str) -> None:
    """Async wrapper for progress callback."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, progress_callback_wrapper, job_id, progress, message)


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
    async_session_maker = get_db_session_factory()
    async with async_session_maker() as db:
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
        broadcast_update(str(job_id), payload)


async def _resolve_provider_for_job(
    db: AsyncSession,
    job: Job,
    workflow: dict[str, object],
    preference: str,
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
            allowed, reason = await router.budget_tracker.check_budget(provider.id, estimated_cost)
            if not allowed:
                raise ValueError(f"Assigned provider '{provider.name}' unavailable: {reason}")

        return provider, provider_instance, estimated_cost, router, "Assigned provider"

    provider, provider_instance, reason = await router.select_provider(
        preference=preference,
        workflow=workflow,
    )
    estimated_cost = Decimal(str(await provider_instance.estimate_cost(workflow)))
    return provider, provider_instance, estimated_cost, router, reason


async def _run_local_job(
    job_id: str,
    template_name: str | None,
    input_data: dict[str, object],
) -> tuple[str, str | None]:
    video_path, preview_path = await process_job_video(
        job_id=job_id,
        template_name=template_name,
        input_data=input_data,
        progress_callback=lambda p, m: async_progress_callback(job_id, p, m),
    )

    relative_video = str(Path(video_path).relative_to(settings.storage_path))
    relative_preview = (
        str(Path(preview_path).relative_to(settings.storage_path)) if preview_path else None
    )
    return relative_video, relative_preview


async def _run_runpod_job(
    job_id: str,
    workflow: dict[str, object],
    provider_instance,
) -> tuple[str, str | None]:
    run_id = await provider_instance.queue_prompt(workflow)
    result = await provider_instance.wait_for_completion(
        run_id,
        progress_callback=lambda p, m: progress_callback_wrapper(job_id, p, m),
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
    input_data: dict[str, object],
) -> str:
    from app.services.model_registry import MODELS

    prompt = input_data.get("prompt", "")
    negative_prompt = input_data.get("negative_prompt", "")

    selected_model = None
    model_id = model_preference or "poe_veo31"

    if model_id in MODELS:
        selected_model = MODELS[model_id]
    else:
        for model in MODELS.values():
            if model.provider == "poe" and model_id in model.id:
                selected_model = model
                break

    if not selected_model:
        selected_model = MODELS.get("poe_veo31")

    poe_model_id = getattr(selected_model, "poe_model_id", "Veo-3.1")
    capabilities = getattr(selected_model, "capabilities", [])

    duration = input_data.get("duration", 10)
    aspect_ratio = input_data.get("aspect_ratio", "16:9")
    resolution = input_data.get("resolution", "1080p")

    is_image = "image-generation" in capabilities

    output_path = Path(settings.storage_path) / "output" / job_id

    if is_image:
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / "image.png"
        job_id_result, image_data = await provider_instance.generate_image(
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
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / "video.mp4"
        job_id_result, video_data = await provider_instance.generate_video(
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


def _as_decimal(value: float | int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


@celery_app.task(bind=True, time_limit=TASK_TIME_LIMIT)
def process_video_job(self, job_id: str, provider_preference: str = "auto") -> dict:
    job_uuid = UUID(job_id)

    async def run() -> dict:
        async_session_maker = get_db_session_factory()

        await update_job_status(job_uuid, "queued", 0)

        async with async_session_maker() as db:
            result = await db.execute(select(Job).where(Job.id == job_uuid))
            job = result.scalar_one_or_none()
            if not job:
                raise ValueError(f"Job {job_id} not found")

            input_data = job.input_data or {}
            template_name = await get_template_name(job.template_id)
            preference = job.provider_preference or provider_preference

            if not job.provider_preference:
                job.provider_preference = preference

            model_preference = job.model_preference

            template = None
            result = await db.execute(select(Template).where(Template.id == job.template_id))
            template = result.scalar_one_or_none()
            workflow = template.config if template else {}

            router = None
            semaphore = None

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

                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Job {job_id}: provider_type={provider_record.provider_type}, provider_id={provider_record.id}")

                if provider_record.provider_type == "comfyui_direct":
                    logger.info(f"Job {job_id}: Creating semaphore")
                    semaphore = ComfyUISemaphore(
                        key=f"{COMFYUI_SEMAPHORE_KEY}:{provider_record.id}",
                        max_concurrent=provider_record.config.get(
                            "max_concurrent_jobs", COMFYUI_MAX_CONCURRENT
                        ),
                    )
                    logger.info(f"Job {job_id}: Acquiring semaphore")
                    acquired = await semaphore.acquire(job_id, timeout=3600)
                    logger.info(f"Job {job_id}: Semaphore acquired: {acquired}")
                    if not acquired:
                        await update_job_status(
                            job_uuid,
                            "failed",
                            0,
                            error_message="GPU queue is full. Job will be retried.",
                        )
                        return {"status": "failed", "error": "Queue full", "job_id": job_id}

                    relative_video, relative_preview = await _run_local_job(
                        job_id,
                        template_name,
                        input_data,
                    )

                    await update_job_status(
                        job_uuid,
                        "completed",
                        100,
                        output_path=relative_video,
                        preview_path=relative_preview,
                    )
                    return {"status": "completed", "job_id": job_id}

                elif provider_record.provider_type == "poe":
                    relative_video = await _run_poe_job(
                        job_id,
                        provider_instance,
                        model_preference,
                        input_data,
                    )

                    await update_job_status(
                        job_uuid,
                        "completed",
                        100,
                        output_path=relative_video,
                    )
                    return {"status": "completed", "job_id": job_id}

                elif provider_record.provider_type == "runpod":
                    run_result_video, run_result_preview = await _run_runpod_job(
                        job_id, workflow, provider_instance
                    )

                    if run_result_video.startswith(settings.storage_path):
                        relative_video = str(Path(run_result_video).relative_to(settings.storage_path))
                    else:
                        relative_video = str(run_result_video)

                    if run_result_preview:
                        if run_result_preview.startswith(settings.storage_path):
                            relative_preview = str(
                                Path(run_result_preview).relative_to(settings.storage_path)
                            )
                        else:
                            relative_preview = str(run_result_preview)
                    else:
                        relative_preview = None

                    actual_cost = _as_decimal(estimated_cost)
                    if actual_cost and provider_record.provider_type == "runpod":
                        await router.budget_tracker.record_spend(provider_record.id, actual_cost)

                    await update_job_status(
                        job_uuid,
                        "completed",
                        100,
                        output_path=relative_video,
                        preview_path=relative_preview,
                        actual_cost=actual_cost,
                    )
                    return {"status": "completed", "job_id": job_id}

                else:
                    raise ValueError(f"Unknown provider type: {provider_record.provider_type}")

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
                return {"status": "failed", "error": error_message, "job_id": job_id}

            finally:
                if semaphore:
                    await semaphore.release()

                if router is not None:
                    try:
                        await router.shutdown()
                    except Exception:
                        pass

    return asyncio.run(run())


@celery_app.task
def send_heartbeat() -> dict:
    async def run() -> dict:
        async_session_maker = get_db_session_factory()
        async with async_session_maker() as db:
            registry = WorkerRegistry(db)

            result = await db.execute(
                select(Provider).where(
                    Provider.provider_type == "comfyui_direct", Provider.is_active == True
                )
            )
            provider = result.scalar_one_or_none()

            if provider:
                worker_id = settings.worker_id
                worker_name = settings.worker_name

                await registry.register(
                    worker_id=worker_id,
                    name=worker_name,
                    provider_id=provider.id,
                    capabilities={
                        "gpu": "Radeon 890M",
                        "max_concurrent": settings.comfyui_max_concurrent,
                    },
                )
                await registry.heartbeat(worker_id)

        return {"status": "ok"}

    return asyncio.run(run())


@celery_app.task
def cleanup_stale_workers() -> dict:
    async def run() -> dict:
        async_session_maker = get_db_session_factory()
        async with async_session_maker() as db:
            registry = WorkerRegistry(db)
            count = await registry.cleanup_stale_workers()
            if count > 0:
                print(f"[Worker] Cleaned up {count} stale workers")
        return {"cleaned": count}

    return asyncio.run(run())


@celery_app.task
def reset_daily_budgets() -> dict:
    async def run() -> dict:
        async_session_maker = get_db_session_factory()
        async with async_session_maker() as db:
            result = await db.execute(select(Provider))
            providers = result.scalars().all()

            tracker = BudgetTracker(db)
            for provider in providers:
                await tracker.reset_provider_spend(provider.id)

        return {"reset_count": len(providers)}

    return asyncio.run(run())


@celery_app.task
def generate_preview(job_id: str) -> dict:
    from app.services.video_processor import VideoProcessor

    async def run() -> dict:
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

    return asyncio.run(run())


@celery_app.task
def merge_videos(job_id: str, segment_paths: list[str]) -> dict:
    from app.services.video_processor import VideoProcessor

    async def run() -> dict:
        output_path = Path(settings.storage_path) / "output" / job_id / "merged.mp4"
        await VideoProcessor.merge_videos(segment_paths, str(output_path))
        return {
            "status": "completed",
            "job_id": job_id,
            "segments": len(segment_paths),
            "output": str(output_path),
        }

    return asyncio.run(run())
