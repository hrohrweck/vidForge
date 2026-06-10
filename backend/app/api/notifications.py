"""Notification API endpoints for user and admin error event management.

User endpoints (``/api/notifications``):
- List, count, and mark-as-read for the authenticated user's events.
- System events (``user_id IS NULL``) are never exposed to regular users.
- The ``details`` field is never included in user-facing responses.

Admin endpoints (``/api/admin/notifications``):
- Full visibility across all events including system events.
- ``GET /{event_id}`` includes the ``details`` blob.
- ``DELETE /{event_id}`` removes an event row.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import require_admin
from app.api.auth import get_current_user, get_current_user_from_bearer_or_cookie
from app.api.schemas.notifications import (
    ErrorEventListResponse,
    ErrorEventResponse,
    MarkReadResponse,
)
from app.database import ErrorEvent, User, get_db

# ---------------------------------------------------------------------------
# User-facing router (mounted at /api/notifications)
# ---------------------------------------------------------------------------

router = APIRouter()

_MAX_PAGE_SIZE = 200


@router.get("", response_model=ErrorEventListResponse)
async def list_notifications(
    severity: list[str] | None = Query(None),
    origin: list[str] | None = Query(None),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ErrorEventListResponse:
    """Return paginated error events for the authenticated user.

    System events (``user_id IS NULL``) are excluded.
    """
    base_query = select(ErrorEvent).where(
        ErrorEvent.user_id == current_user.id,
        ErrorEvent.user_id.is_not(None),
    )

    # Apply filters
    if severity:
        base_query = base_query.where(ErrorEvent.severity.in_(severity))
    if origin:
        base_query = base_query.where(ErrorEvent.origin.in_(origin))
    if unread_only:
        base_query = base_query.where(ErrorEvent.read_at.is_(None))

    # Total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Unread count (ignores pagination but respects filters except unread_only)
    unread_base_query = select(ErrorEvent).where(
        ErrorEvent.user_id == current_user.id,
        ErrorEvent.user_id.is_not(None),
        ErrorEvent.read_at.is_(None),
    )
    if severity:
        unread_base_query = unread_base_query.where(ErrorEvent.severity.in_(severity))
    if origin:
        unread_base_query = unread_base_query.where(ErrorEvent.origin.in_(origin))

    unread_query = select(func.count()).select_from(unread_base_query.subquery())
    unread_result = await db.execute(unread_query)
    unread_count = unread_result.scalar() or 0

    # Fetch page
    items_query = (
        base_query.order_by(ErrorEvent.created_at.desc()).offset(offset).limit(limit)
    )
    items_result = await db.execute(items_query)
    items = list(items_result.scalars().all())

    return ErrorEventListResponse(
        items=[ErrorEventResponse.model_validate(e) for e in items],
        total=total,
        unread_count=unread_count,
    )


@router.get("/unread-count", response_model=dict[str, int])
async def get_unread_count(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Return the number of unread notifications for the current user."""
    query = (
        select(func.count())
        .select_from(ErrorEvent)
        .where(
            ErrorEvent.user_id == current_user.id,
            ErrorEvent.user_id.is_not(None),
            ErrorEvent.read_at.is_(None),
        )
    )
    result = await db.execute(query)
    count = result.scalar() or 0
    return {"unreadCount": count}


@router.post("/{event_id}/read", response_model=MarkReadResponse)
async def mark_notification_read(
    event_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> MarkReadResponse:
    """Mark a single notification as read.

    Only the owning user can mark their own events.
    """
    stmt = (
        update(ErrorEvent)
        .where(
            ErrorEvent.id == event_id,
            ErrorEvent.user_id == current_user.id,
            ErrorEvent.user_id.is_not(None),
        )
        .values(read_at=datetime.utcnow())
        .returning(ErrorEvent.id)
    )
    result = await db.execute(stmt)
    await db.commit()

    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    return MarkReadResponse(success=True)


@router.post("/mark-all-read", response_model=MarkReadResponse)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> MarkReadResponse:
    """Mark all unread notifications as read for the current user."""
    stmt = (
        update(ErrorEvent)
        .where(
            ErrorEvent.user_id == current_user.id,
            ErrorEvent.user_id.is_not(None),
            ErrorEvent.read_at.is_(None),
        )
        .values(read_at=datetime.utcnow())
    )
    await db.execute(stmt)
    await db.commit()
    return MarkReadResponse(success=True)


# ---------------------------------------------------------------------------
# Admin router (mounted at /api/admin)
# ---------------------------------------------------------------------------

admin_router = APIRouter()


class AdminErrorEventResponse(ErrorEventResponse):
    """Admin-facing event representation — includes ``details``."""

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    details: dict | None = None


class AdminErrorEventListResponse(BaseModel):
    """Paginated envelope for admin notification listing."""

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    items: list[AdminErrorEventResponse]
    total: int
    unread_count: int


@admin_router.get("/notifications", response_model=AdminErrorEventListResponse)
async def admin_list_notifications(
    severity: list[str] | None = Query(None),
    origin: list[str] | None = Query(None),
    user_id: UUID | None = Query(None),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminErrorEventListResponse:
    """Return paginated error events for admin view.

    Includes system events (``user_id IS NULL``) and all user events.
    """
    base_query = select(ErrorEvent)

    if severity:
        base_query = base_query.where(ErrorEvent.severity.in_(severity))
    if origin:
        base_query = base_query.where(ErrorEvent.origin.in_(origin))
    if user_id is not None:
        base_query = base_query.where(ErrorEvent.user_id == user_id)
    if unread_only:
        base_query = base_query.where(ErrorEvent.read_at.is_(None))

    # Total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Unread count
    unread_base = select(ErrorEvent).where(ErrorEvent.read_at.is_(None))
    if severity:
        unread_base = unread_base.where(ErrorEvent.severity.in_(severity))
    if origin:
        unread_base = unread_base.where(ErrorEvent.origin.in_(origin))
    if user_id is not None:
        unread_base = unread_base.where(ErrorEvent.user_id == user_id)

    unread_query = select(func.count()).select_from(unread_base.subquery())
    unread_result = await db.execute(unread_query)
    unread_count = unread_result.scalar() or 0

    # Fetch page
    items_query = (
        base_query.order_by(ErrorEvent.created_at.desc()).offset(offset).limit(limit)
    )
    items_result = await db.execute(items_query)
    items = list(items_result.scalars().all())

    return AdminErrorEventListResponse(
        items=[AdminErrorEventResponse.model_validate(e) for e in items],
        total=total,
        unread_count=unread_count,
    )


@admin_router.get("/notifications/{event_id}", response_model=AdminErrorEventResponse)
async def admin_get_notification(
    event_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminErrorEventResponse:
    """Return a single error event with full ``details`` for admin."""
    result = await db.execute(select(ErrorEvent).where(ErrorEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return AdminErrorEventResponse.model_validate(event)


@admin_router.delete("/notifications/{event_id}", response_model=dict[str, bool])
async def admin_delete_notification(
    event_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Delete an error event (admin only)."""
    result = await db.execute(select(ErrorEvent).where(ErrorEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    await db.delete(event)
    await db.commit()
    return {"success": True}
