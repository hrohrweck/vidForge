import asyncio
import json
from datetime import datetime
from uuid import UUID

import redis
from celery import shared_task
from sqlalchemy import select

from app.config import get_settings
from app.database import Job, async_session
from app.workers.celery_app import celery_app


def get_redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


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
    async with async_session() as db:
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


@celery_app.task(bind=True)
def process_video_job(self, job_id: str) -> dict:
    job_uuid = UUID(job_id)

    asyncio.run(update_job_status(job_uuid, "processing", 0))

    try:
        asyncio.run(update_job_status(job_uuid, "processing", 10))

        asyncio.run(update_job_status(job_uuid, "processing", 50))

        asyncio.run(update_job_status(job_uuid, "processing", 90))

        asyncio.run(
            update_job_status(
                job_uuid,
                "completed",
                100,
                output_path=f"output/{job_id}/video.mp4",
                preview_path=f"output/{job_id}/preview.mp4",
            )
        )

        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        asyncio.run(update_job_status(job_uuid, "failed", 0, error_message=str(e)))
        return {"status": "failed", "error": str(e), "job_id": job_id}


@celery_app.task
def generate_preview(job_id: str) -> dict:
    return {"status": "completed", "job_id": job_id}


@celery_app.task
def merge_videos(job_id: str, segment_paths: list[str]) -> dict:
    return {"status": "completed", "job_id": job_id, "segments": len(segment_paths)}
