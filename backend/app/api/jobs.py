import csv
import io
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import Job, Template, User, get_db
from app.workers.tasks import process_scene_video_job, process_video_job

router = APIRouter()


class JobCreate(BaseModel):
    title: str = "Untitled Video"
    template_id: UUID | None = None
    project_id: UUID | None = None
    input_data: dict[str, Any] | None = None
    auto_start: bool = True
    provider_preference: str = "auto"
    model_preference: str | None = None


class BatchJobCreate(BaseModel):
    template_id: UUID
    project_id: UUID | None = None
    jobs: list[dict[str, Any]]
    auto_start: bool = True
    provider_preference: str = "auto"
    model_preference: str | None = None


class BatchJobResponse(BaseModel):
    created_count: int
    job_ids: list[str]


PROVIDER_PREFERENCES = {"auto"}


def _normalize_provider_preference(value: str) -> str:
    """Normalize provider preference to accepted values.

    Accepts:
    - "auto" - automatically select provider based on availability
    - A valid provider UUID - use that specific provider
    - Legacy provider types (comfyui_direct, runpod, poe) - converted to "auto" for backward compatibility
    """
    if value in PROVIDER_PREFERENCES:
        return value

    # If it's a UUID (provider ID), pass through - will be validated at job processing time
    try:
        UUID(value)
        return value
    except ValueError:
        pass

    # Legacy provider types are now treated as "auto"
    legacy_types = {"comfyui_direct", "runpod", "poe"}
    if value in legacy_types:
        return "auto"

    return "auto"


class JobResponse(BaseModel):
    id: UUID
    title: str
    project_id: UUID | None = None
    status: str
    stage: str
    progress: int
    input_data: dict[str, Any] | None
    output_path: str | None
    preview_path: str | None
    thumbnail_path: str | None
    error_message: str | None
    provider_id: UUID | None
    provider_type: str | None
    provider_preference: str
    model_preference: str | None
    estimated_cost: float | None
    actual_cost: float | None
    workflow_type: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Job]:
    query = select(Job).where(Job.user_id == current_user.id).order_by(Job.created_at.desc())
    if status:
        query = query.where(Job.status == status)
    if project_id:
        query = query.where(Job.project_id == UUID(project_id))
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
    provider_preference = _normalize_provider_preference(job_data.provider_preference)

    job = Job(
        title=job_data.title,
        user_id=current_user.id,
        template_id=job_data.template_id,
        input_data=job_data.input_data or {},
        provider_preference=provider_preference,
        model_preference=job_data.model_preference,
        project_id=job_data.project_id,
    )

    if job_data.template_id:
        result = await db.execute(select(Template).where(Template.id == job_data.template_id))
        template = result.scalar_one_or_none()
        if template:
            workflow_type = template.config.get("workflow_type")
            if workflow_type == "scene_based":
                job.workflow_type = "scene_based"

    db.add(job)
    await db.commit()
    await db.refresh(job)

    if job_data.auto_start:
        if job.workflow_type == "scene_based":
            process_scene_video_job.delay(str(job.id), stage="planning")
        else:
            process_video_job.delay(str(job.id), provider_preference=provider_preference)

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

    if job.workflow_type == "scene_based":
        process_scene_video_job.delay(str(job.id), stage="planning")
    else:
        process_video_job.delay(str(job.id), provider_preference=job.provider_preference)
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


class JobPatchRequest(BaseModel):
    input_data: dict | None = None


@router.patch("/{job_id}", response_model=JobResponse)
async def patch_job(
    job_id: UUID,
    data: JobPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if data.input_data is not None:
        job.input_data = {**(job.input_data or {}), **data.input_data}
    await db.commit()
    await db.refresh(job)
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


@router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ("failed", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job with status: {job.status}. Only failed or completed jobs can be retried.",
        )

    job.status = "pending"
    job.progress = 0
    job.error_message = None
    job.actual_cost = None
    job.started_at = None
    job.completed_at = None
    await db.commit()
    await db.refresh(job)

    if job.workflow_type == "scene_based":
        process_scene_video_job.delay(str(job.id), stage="planning")
    else:
        process_video_job.delay(str(job.id), provider_preference=job.provider_preference)

    return job


@router.post("/batch", response_model=BatchJobResponse)
async def create_batch_jobs(
    batch_data: BatchJobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Template).where(Template.id == batch_data.template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    provider_preference = _normalize_provider_preference(batch_data.provider_preference)
    workflow_type = template.config.get("workflow_type", "standard")
    is_scene_based = workflow_type == "scene_based"

    jobs = []
    job_ids = []
    for job_input in batch_data.jobs:
        job = Job(
            user_id=current_user.id,
            template_id=batch_data.template_id,
            input_data=job_input,
            provider_preference=provider_preference,
            model_preference=batch_data.model_preference,
            project_id=batch_data.project_id,
            workflow_type=workflow_type if is_scene_based else None,
        )
        jobs.append(job)
        db.add(job)
        await db.flush()
        job_ids.append(job.id)

    await db.commit()

    if batch_data.auto_start:
        for job_id in job_ids:
            if is_scene_based:
                process_scene_video_job.delay(str(job_id), stage="planning")
            else:
                process_video_job.delay(str(job_id), provider_preference=provider_preference)

    return {"created_count": len(jobs), "job_ids": [str(j) for j in job_ids]}


@router.post("/batch/csv", response_model=BatchJobResponse)
async def create_jobs_from_csv(
    template_id: UUID,
    file: UploadFile = File(...),
    auto_start: bool = True,
    provider_preference: str = "auto",
    model_preference: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    provider_preference = _normalize_provider_preference(provider_preference)
    workflow_type = template.config.get("workflow_type", "standard")
    is_scene_based = workflow_type == "scene_based"

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        decoded = content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no headers")

    jobs = []
    job_ids = []
    for row in reader:
        job = Job(
            user_id=current_user.id,
            template_id=template_id,
            input_data=dict(row),
            provider_preference=provider_preference,
            model_preference=model_preference,
            workflow_type=workflow_type if is_scene_based else None,
        )
        jobs.append(job)
        db.add(job)
        await db.flush()
        job_ids.append(job.id)

    await db.commit()

    if auto_start:
        for job_id in job_ids:
            if is_scene_based:
                process_scene_video_job.delay(str(job_id), stage="planning")
            else:
                process_video_job.delay(str(job_id), provider_preference=provider_preference)

    return {"created_count": len(jobs), "job_ids": [str(j) for j in job_ids]}


@router.get("/{job_id}/download")
async def download_job_output(
    job_id: UUID,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Download the final exported video for a completed job.

    Accepts auth via ``?token=`` query param for browser-initiated downloads.
    """
    from pathlib import Path

    from fastapi.responses import FileResponse
    from jose import jwt as pyjwt

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    settings = get_settings()
    current_user: User | None = None

    try:
        payload = pyjwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if user_id:
            result = await db.execute(select(User).where(User.id == UUID(user_id)))
            current_user = result.scalar_one_or_none()
    except Exception:
        pass

    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.output_path:
        raise HTTPException(status_code=404, detail="Job has no output file")

    file_path = Path(settings.storage_path) / job.output_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found on disk")

    safe_title = "".join(c for c in job.title if c.isalnum() or c in " -_").strip() or "video"
    ext = file_path.suffix or ".mp4"
    filename = f"{safe_title}{ext}"

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=filename,
    )
