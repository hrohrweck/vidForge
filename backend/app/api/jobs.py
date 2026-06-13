import csv
import io
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user_from_bearer_or_cookie
from app.database import Avatar, Job, JobAvatar, JobObjectRef, ObjectRef, Template, User, get_db
from app.dependencies.rate_limit import AuthenticatedRateLimiter
from app.plugins.registry import get_plugin
from app.workers.tasks import process_scene_video_job, process_video_job

router = APIRouter()

job_create_rate_limiter = AuthenticatedRateLimiter(times=30, seconds=60)


class JobCreate(BaseModel):
    title: str = "Untitled Video"
    template_id: UUID | None = None
    project_id: UUID | None = None
    input_data: dict[str, Any] | None = None
    auto_start: bool = True
    provider_preference: str = "auto"
    model_preference: str | None = None
    chat_conversation_id: UUID | None = None
    chat_message_id: UUID | None = None

    @field_validator("template_id", mode="before")
    @classmethod
    def validate_template_id(cls, v: Any) -> Any:
        if v is None:
            return v
        try:
            return UUID(str(v))
        except ValueError:
            raise ValueError("Template not found")


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


def _validate_job_input(
    template: Template | None, input_data: dict[str, Any] | None
) -> dict[str, Any]:
    if template is None:
        return input_data or {}

    plugin_id = template.config.get("plugin_id") if template.config else None
    if not plugin_id:
        return input_data or {}

    plugin = get_plugin(plugin_id)
    if plugin is None:
        return input_data or {}

    schema_cls = plugin.get_input_schema()
    if schema_cls is None:
        return input_data or {}

    try:
        data = input_data if input_data is not None else {}
        # Dump in JSON mode so UUIDs and other non-JSON types become strings
        # before the dict is stored in the JSONB input_data column.
        return schema_cls.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"errors": errors},
        )


class JobAvatarDetail(BaseModel):
    avatar_id: UUID
    avatar_name: str
    role: str | None = None
    consistency_strategy_override: str | None = None


class JobObjectDetail(BaseModel):
    object_id: UUID
    object_name: str
    role: str | None = None
    importance_score: float | None = None
    category: str | None = None
    description: str | None = None
    primary_image_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


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
    avatars: list[JobAvatarDetail] | None = None

    model_config = ConfigDict(from_attributes=True)


def _populate_job_avatars(job: Job) -> None:
    if job.avatar_assignments:
        job.avatars = [  # type: ignore[attr-defined]
            JobAvatarDetail(
                avatar_id=ja.avatar_id,
                avatar_name=ja.avatar.name if ja.avatar else "Unknown",
                role=ja.role,
                consistency_strategy_override=ja.consistency_strategy_override,
            )
            for ja in job.avatar_assignments
        ]


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> list[Job]:
    query = (
        select(Job)
        .options(selectinload(Job.avatar_assignments).selectinload(JobAvatar.avatar))
        .where(Job.user_id == current_user.id)
        .order_by(Job.created_at.desc())
    )
    if status:
        query = query.where(Job.status == status)
    if project_id:
        query = query.where(Job.project_id == UUID(project_id))
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    jobs = list(result.scalars().all())
    for job in jobs:
        _populate_job_avatars(job)
    return jobs


@router.post("", response_model=JobResponse)
async def create_job(
    job_data: JobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(job_create_rate_limiter),
) -> Job:
    provider_preference = _normalize_provider_preference(job_data.provider_preference)

    template: Template | None = None
    if job_data.template_id:
        result = await db.execute(select(Template).where(Template.id == job_data.template_id))
        template = result.scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

    validated_input = _validate_job_input(template, job_data.input_data)

    job = Job(
        title=job_data.title,
        user_id=current_user.id,
        template_id=job_data.template_id,
        input_data=validated_input,
        provider_preference=provider_preference,
        model_preference=job_data.model_preference,
        project_id=job_data.project_id,
        chat_conversation_id=job_data.chat_conversation_id,
        chat_message_id=job_data.chat_message_id,
    )

    if template:
        workflow_type = template.config.get("workflow_type")
        if workflow_type == "scene_based":
            job.workflow_type = "scene_based"

    # Flush the job early so job.id is populated for JobAvatar rows
    db.add(job)
    await db.flush()

    avatar_assignments: list[dict[str, Any]] = []
    if isinstance(job.input_data, dict):
        avatar_assignments = job.input_data.get("avatars", []) or []

    avatar_errors: list[str] = []
    avatar_rows: list[JobAvatar] = []
    avatar_name_map: dict[UUID, str] = {}
    seen_avatar_ids: set[UUID] = set()

    for i, assignment in enumerate(avatar_assignments):
        avatar_id_str = assignment.get("avatar_id")
        try:
            avatar_id = UUID(str(avatar_id_str))
        except (ValueError, TypeError, AttributeError):
            avatar_errors.append(f"avatars[{i}].avatar_id: invalid UUID '{avatar_id_str}'")
            continue

        if avatar_id in seen_avatar_ids:
            continue
        seen_avatar_ids.add(avatar_id)

        av_result = await db.execute(
            select(Avatar).where(
                Avatar.id == avatar_id,
                Avatar.user_id == current_user.id,
                Avatar.deleted_at.is_(None),
            )
        )
        avatar = av_result.scalar_one_or_none()
        if not avatar:
            avatar_errors.append(
                f"avatars[{i}].avatar_id: avatar '{avatar_id_str}' not found or access denied"
            )
            continue

        avatar_name_map[avatar_id] = avatar.name
        avatar_rows.append(
            JobAvatar(
                job_id=job.id,
                avatar_id=avatar_id,
                role=assignment.get("role"),
                consistency_strategy_override=assignment.get("consistency_strategy_override"),
            )
        )

    if avatar_errors:
        raise HTTPException(status_code=422, detail={"errors": avatar_errors})

    for row in avatar_rows:
        db.add(row)
    await db.commit()
    await db.refresh(job)

    if avatar_rows:
        avatars_response = [
            JobAvatarDetail(
                avatar_id=row.avatar_id,
                avatar_name=avatar_name_map[row.avatar_id],
                role=row.role,
                consistency_strategy_override=row.consistency_strategy_override,
            )
            for row in avatar_rows
        ]
        job.avatars = avatars_response  # type: ignore[attr-defined]

    if job_data.auto_start:
        if job.workflow_type == "scene_based":
            process_scene_video_job.delay(str(job.id), stage="planning")
        else:
            process_video_job.delay(str(job.id), provider_preference=provider_preference)

    return job


@router.post("/{job_id}/start")
async def start_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.avatar_assignments).selectinload(JobAvatar.avatar))
        .where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _populate_job_avatars(job)
    return job


class JobPatchRequest(BaseModel):
    input_data: dict | None = None


@router.patch("/{job_id}", response_model=JobResponse)
async def patch_job(
    job_id: UUID,
    data: JobPatchRequest,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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


@router.get("/{job_id}/objects", response_model=list[JobObjectDetail])
async def get_job_objects(
    job_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> list[JobObjectDetail]:
    """Return object references assigned to a job with role/importance metadata."""
    result = await db.execute(
        select(JobObjectRef, ObjectRef)
        .join(ObjectRef, JobObjectRef.object_ref_id == ObjectRef.id)
        .join(Job, JobObjectRef.job_id == Job.id)
        .options(selectinload(ObjectRef.images))
        .where(
            JobObjectRef.job_id == job_id,
            Job.user_id == current_user.id,
            ObjectRef.deleted_at.is_(None),
        )
    )
    rows = result.all()
    return [
        JobObjectDetail(
            object_id=obj_ref.id,
            object_name=obj_ref.name,
            role=assoc.role,
            importance_score=assoc.importance_score,
            category=obj_ref.category,
            description=obj_ref.description,
            primary_image_path=(
                next((img.storage_path for img in (obj_ref.images or []) if img.is_primary), None)
                if obj_ref.images
                else None
            ),
        )
        for assoc, obj_ref in rows
    ]


@router.delete("/{job_id}")
async def delete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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
        validated_input = _validate_job_input(template, job_input)
        job = Job(
            user_id=current_user.id,
            template_id=batch_data.template_id,
            input_data=validated_input,
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
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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
        validated_input = _validate_job_input(template, dict(row))
        job = Job(
            user_id=current_user.id,
            template_id=template_id,
            input_data=validated_input,
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
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    from pathlib import Path

    from fastapi.responses import FileResponse

    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.output_path:
        raise HTTPException(status_code=404, detail="Job has no output file")

    from app.config import get_settings

    settings = get_settings()
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
