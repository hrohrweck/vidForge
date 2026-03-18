from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import Job, User, get_db

router = APIRouter()
settings = get_settings()


class SystemStats(BaseModel):
    total_users: int
    total_jobs: int
    jobs_today: int
    jobs_this_week: int
    jobs_by_status: dict[str, int]
    jobs_by_template: dict[str, int]
    storage_backend: str
    uptime: str


class RecentJob(BaseModel):
    id: str
    status: str
    progress: int
    created_at: datetime
    user_email: str | None = None

    class Config:
        from_attributes = True


class AdminDashboard(BaseModel):
    stats: SystemStats
    recent_jobs: list[RecentJob]


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/dashboard", response_model=AdminDashboard)
async def get_admin_dashboard(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())

    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    total_jobs_result = await db.execute(select(func.count(Job.id)))
    total_jobs = total_jobs_result.scalar() or 0

    jobs_today_result = await db.execute(
        select(func.count(Job.id)).where(Job.created_at >= today_start)
    )
    jobs_today = jobs_today_result.scalar() or 0

    jobs_this_week_result = await db.execute(
        select(func.count(Job.id)).where(Job.created_at >= week_start)
    )
    jobs_this_week = jobs_this_week_result.scalar() or 0

    jobs_by_status_result = await db.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    )
    jobs_by_status = {row[0]: row[1] for row in jobs_by_status_result.all()}

    recent_jobs_result = await db.execute(select(Job).order_by(Job.created_at.desc()).limit(10))
    recent_jobs = []
    for job in recent_jobs_result.scalars().all():
        user_result = await db.execute(select(User).where(User.id == job.user_id))
        user = user_result.scalar_one_or_none()
        recent_jobs.append(
            {
                "id": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "created_at": job.created_at,
                "user_email": user.email if user else None,
            }
        )

    return {
        "stats": {
            "total_users": total_users,
            "total_jobs": total_jobs,
            "jobs_today": jobs_today,
            "jobs_this_week": jobs_this_week,
            "jobs_by_status": jobs_by_status,
            "jobs_by_template": {},
            "storage_backend": settings.storage_backend,
            "uptime": "N/A",
        },
        "recent_jobs": recent_jobs,
    }


@router.get("/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()

    user_list = []
    for user in users:
        jobs_count_result = await db.execute(
            select(func.count(Job.id)).where(Job.user_id == user.id)
        )
        jobs_count = jobs_count_result.scalar() or 0

        user_list.append(
            {
                "id": str(user.id),
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "created_at": user.created_at,
                "jobs_count": jobs_count,
            }
        )

    return user_list


@router.get("/jobs")
async def list_all_jobs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    query = select(Job).order_by(Job.created_at.desc())

    if status:
        query = query.where(Job.status == status)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()

    job_list = []
    for job in jobs:
        user_result = await db.execute(select(User).where(User.id == job.user_id))
        user = user_result.scalar_one_or_none()

        job_list.append(
            {
                "id": str(job.id),
                "user_id": str(job.user_id),
                "user_email": user.email if user else None,
                "status": job.status,
                "progress": job.progress,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "error_message": job.error_message,
            }
        )

    return job_list


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, str]:
    from uuid import UUID

    result = await db.execute(select(Job).where(Job.id == UUID(job_id)))
    job = result.scalar_one_or_none()

    if not job:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "pending":
        job.status = "cancelled"
        await db.commit()
        return {"status": "cancelled", "job_id": job_id}
    elif job.status == "processing":
        job.status = "cancelled"
        job.error_message = "Cancelled by admin"
        await db.commit()
        return {"status": "cancelled", "job_id": job_id}
    else:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status: {job.status}")


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, str]:
    from uuid import UUID

    result = await db.execute(select(Job).where(Job.id == UUID(job_id)))
    job = result.scalar_one_or_none()

    if not job:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ("failed", "cancelled"):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=f"Cannot retry job with status: {job.status}")

    job.status = "pending"
    job.progress = 0
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    await db.commit()

    from app.workers.tasks import process_video_job

    process_video_job.delay(str(job.id))

    return {"status": "restarted", "job_id": job_id}
