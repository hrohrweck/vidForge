from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import Job, Template, User, get_db
from app.workers.tasks import process_video_job

router = APIRouter()


class JobCreate(BaseModel):
    template_id: UUID | None = None
    input_data: dict[str, Any] | None = None
    auto_start: bool = True


class JobResponse(BaseModel):
    id: UUID
    status: str
    progress: int
    input_data: dict[str, Any] | None
    output_path: str | None
    preview_path: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Job]:
    query = select(Job).where(Job.user_id == current_user.id).order_by(Job.created_at.desc())
    if status:
        query = query.where(Job.status == status)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=JobResponse)
async def create_job(
    job_data: JobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    job = Job(
        user_id=current_user.id,
        template_id=job_data.template_id,
        input_data=job_data.input_data or {},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if job_data.auto_start:
        process_video_job.delay(str(job.id))

    return job


@router.post("/{job_id}/start")
async def start_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot start job with status: {job.status}")

    process_video_job.delay(str(job.id))
    return {"status": "started", "job_id": str(job_id)}


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}")
async def delete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.delete(job)
    await db.commit()
    return {"status": "deleted"}
