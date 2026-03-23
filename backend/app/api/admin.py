from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import (
    Job,
    User,
    Group,
    Permission,
    UserGroup,
    GroupPermission,
    Template,
    get_db,
)
from app.services.permissions import has_permission, get_user_permissions, require_permission

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


# === User Management ===


class UserUpdateRequest(BaseModel):
    is_active: bool | None = None
    is_superuser: bool | None = None
    group_ids: list[UUID] | None = None


class UserDetailResponse(BaseModel):
    id: UUID
    email: str
    is_active: bool
    is_superuser: bool
    groups: list[dict[str, Any]]
    permissions: list[str]
    jobs_count: int
    created_at: datetime


class DeletePreviewResponse(BaseModel):
    user_id: UUID
    email: str
    items_to_delete: dict[str, int]
    total_items: int
    warning: str


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_details(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    permissions = await get_user_permissions(user, db)
    groups = user.groups if hasattr(user, "groups") else []

    jobs_count_result = await db.execute(select(func.count(Job.id)).where(Job.user_id == user.id))
    jobs_count = jobs_count_result.scalar() or 0

    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "groups": [{"id": g.id, "name": g.name, "description": g.description} for g in groups],
        "permissions": permissions,
        "jobs_count": jobs_count,
        "created_at": user.created_at,
    }


@router.get("/users/{user_id}/preview-delete", response_model=DeletePreviewResponse)
async def preview_user_deletion(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    jobs_count = await db.scalar(select(func.count(Job.id)).where(Job.user_id == user_id)) or 0
    templates_count = (
        await db.scalar(select(func.count(Template.id)).where(Template.created_by == user_id)) or 0
    )

    return {
        "user_id": user_id,
        "email": user.email,
        "items_to_delete": {
            "jobs": jobs_count,
            "templates": templates_count,
        },
        "total_items": jobs_count + templates_count,
        "warning": "This action cannot be undone. All user data will be permanently deleted.",
    }


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: UUID,
    update_data: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_id == admin.id and update_data.is_superuser is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")

    if update_data.is_active is not None:
        user.is_active = update_data.is_active
    if update_data.is_superuser is not None:
        user.is_superuser = update_data.is_superuser

    if update_data.group_ids is not None:
        await db.execute(sql_delete(UserGroup).where(UserGroup.user_id == user_id))
        for group_id in update_data.group_ids:
            result = await db.execute(select(Group).where(Group.id == group_id))
            group = result.scalar_one_or_none()
            if group:
                user_group = UserGroup(user_id=user_id, group_id=group_id)
                db.add(user_group)

    await db.commit()
    await db.refresh(user)

    return await get_user_details(user_id, db, admin)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, str]:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(sql_delete(UserGroup).where(UserGroup.user_id == user_id))
    await db.execute(sql_delete(Job).where(Job.user_id == user_id))
    await db.execute(sql_delete(Template).where(Template.created_by == user_id))
    await db.delete(user)
    await db.commit()

    return {"status": "deleted", "user_id": str(user_id)}


# === Group Management ===


class GroupCreateRequest(BaseModel):
    name: str
    description: str | None = None
    permission_ids: list[UUID] | None = None


class GroupUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_ids: list[UUID] | None = None


class GroupResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    permissions: list[dict[str, Any]]
    users_count: int


class PermissionResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    category: str


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    result = await db.execute(select(Group))
    groups = result.scalars().all()

    group_list = []
    for group in groups:
        users_count_result = await db.execute(
            select(func.count(UserGroup.user_id)).where(UserGroup.group_id == group.id)
        )
        users_count = users_count_result.scalar() or 0

        permissions = group.permissions if hasattr(group, "permissions") else []

        group_list.append(
            {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "permissions": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "category": p.category,
                    }
                    for p in permissions
                ],
                "users_count": users_count,
            }
        )

    return group_list


@router.post("/groups", response_model=GroupResponse)
async def create_group(
    group_data: GroupCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    result = await db.execute(select(Group).where(Group.name == group_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Group with this name already exists")

    group = Group(name=group_data.name, description=group_data.description)
    db.add(group)
    await db.flush()

    if group_data.permission_ids:
        for perm_id in group_data.permission_ids:
            result = await db.execute(select(Permission).where(Permission.id == perm_id))
            perm = result.scalar_one_or_none()
            if perm:
                gp = GroupPermission(group_id=group.id, permission_id=perm_id)
                db.add(gp)

    await db.commit()
    await db.refresh(group)

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "permissions": [],
        "users_count": 0,
    }


@router.patch("/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: UUID,
    group_data: GroupUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group_data.name is not None:
        existing = await db.execute(
            select(Group).where(Group.name == group_data.name, Group.id != group_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Group with this name already exists")
        group.name = group_data.name

    if group_data.description is not None:
        group.description = group_data.description

    if group_data.permission_ids is not None:
        await db.execute(sql_delete(GroupPermission).where(GroupPermission.group_id == group_id))
        for perm_id in group_data.permission_ids:
            result = await db.execute(select(Permission).where(Permission.id == perm_id))
            perm = result.scalar_one_or_none()
            if perm:
                gp = GroupPermission(group_id=group_id, permission_id=perm_id)
                db.add(gp)

    await db.commit()
    await db.refresh(group)

    users_count_result = await db.execute(
        select(func.count(UserGroup.user_id)).where(UserGroup.group_id == group.id)
    )
    users_count = users_count_result.scalar() or 0
    permissions = group.permissions if hasattr(group, "permissions") else []

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "permissions": [
            {"id": p.id, "name": p.name, "description": p.description, "category": p.category}
            for p in permissions
        ],
        "users_count": users_count,
    }


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, str]:
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group.name in ("users", "admins"):
        raise HTTPException(status_code=400, detail=f"Cannot delete system group '{group.name}'")

    await db.execute(sql_delete(UserGroup).where(UserGroup.group_id == group_id))
    await db.execute(sql_delete(GroupPermission).where(GroupPermission.group_id == group_id))
    await db.delete(group)
    await db.commit()

    return {"status": "deleted", "group_id": str(group_id)}


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    result = await db.execute(select(Permission).order_by(Permission.category, Permission.name))
    permissions = result.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "category": p.category,
        }
        for p in permissions
    ]
