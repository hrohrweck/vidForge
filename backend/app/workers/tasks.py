import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID

import redis
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Job, Template
from app.services.video_generator import process_job_video
from app.workers.celery_app import celery_app

settings = get_settings()


def get_db_session_factory():
    engine = create_async_engine(settings.database_url, echo=settings.debug)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url)


def broadcast_update(job_id: str, message: dict) -> None:
    r = get_redis()
    r.publish(f"job:{job_id}", json.dumps(message))


async def update_job_status(
    job_id: UUID,
    status: str,
    progress: int = 0,
    error_message: str | None = None,
    output_path: str | None = None,
    preview_path: str | None = None,
) -> None:
    async_session_maker = get_db_session_factory()
    async with async_session_maker() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = status
            job.progress = progress
            if error_message:
                job.error_message = error_message
            if output_path:
                job.output_path = output_path
            if preview_path:
                job.preview_path = preview_path
            if status == "processing" and not job.started_at:
                job.started_at = datetime.utcnow()
            if status in ("completed", "failed"):
                job.completed_at = datetime.utcnow()
            await db.commit()

    broadcast_update(
        str(job_id),
        {
            "type": "progress" if status == "processing" else status,
            "job_id": str(job_id),
            "progress": progress,
            "status": status,
            "error": error_message,
            "output_path": output_path,
            "preview_path": preview_path,
        },
    )


async def get_template_name(template_id: UUID | None) -> str:
    if not template_id:
        return "prompt_to_video"
    async_session_maker = get_db_session_factory()
    async with async_session_maker() as db:
        result = await db.execute(select(Template).where(Template.id == template_id))
        template = result.scalar_one_or_none()
        if template:
            config = template.config
            return config.get("template_file", "prompt_to_video")
    return "prompt_to_video"


async def progress_callback_wrapper(job_id: UUID, progress: int, message: str):
    await update_job_status(job_id, "processing", progress)
    broadcast_update(str(job_id), {"type": "status", "message": message})


@celery_app.task(bind=True)
def process_video_job(self, job_id: str) -> dict:
    job_uuid = UUID(job_id)

    async def run():
        await update_job_status(job_uuid, "processing", 0)

        async_session_maker = get_db_session_factory()
        async with async_session_maker() as db:
            result = await db.execute(select(Job).where(Job.id == job_uuid))
            job = result.scalar_one_or_none()
            if not job:
                raise ValueError(f"Job {job_id} not found")

            input_data = job.input_data or {}
            template_name = await get_template_name(job.template_id)

        try:
            video_path, preview_path = await process_job_video(
                job_id=job_id,
                template_name=template_name,
                input_data=input_data,
                progress_callback=lambda p, m: progress_callback_wrapper(job_uuid, p, m),
            )

            relative_video = str(Path(video_path).relative_to(settings.storage_path))
            relative_preview = (
                str(Path(preview_path).relative_to(settings.storage_path)) if preview_path else None
            )

            await update_job_status(
                job_uuid,
                "completed",
                100,
                output_path=relative_video,
                preview_path=relative_preview,
            )

            return {"status": "completed", "job_id": job_id}

        except Exception as e:
            await update_job_status(job_uuid, "failed", 0, error_message=str(e))
            return {"status": "failed", "error": str(e), "job_id": job_id}

    return asyncio.run(run())


@celery_app.task
def generate_preview(job_id: str) -> dict:
    from app.services.video_processor import VideoProcessor

    async def run():
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

    async def run():
        output_path = Path(settings.storage_path) / "output" / job_id / "merged.mp4"
        await VideoProcessor.merge_videos(segment_paths, str(output_path))
        return {
            "status": "completed",
            "job_id": job_id,
            "segments": len(segment_paths),
            "output": str(output_path),
        }

    return asyncio.run(run())
