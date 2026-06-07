import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database import ObjectRef, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ObjectRefImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    storage_path: str
    is_primary: bool
    sort_order: int
    width: int | None = None
    height: int | None = None


class ObjectRefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None = None
    visual_properties: dict | None = None
    category: str | None = None
    images: list[ObjectRefImageResponse] = []
    job_count: int = 0
    created_at: datetime
    updated_at: datetime


class ObjectRefListResponse(BaseModel):
    objects: list[ObjectRefResponse]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _object_ref_to_response(obj: ObjectRef) -> ObjectRefResponse:
    """Convert ORM ObjectRef to ObjectRefResponse."""
    return ObjectRefResponse(
        id=obj.id,
        user_id=obj.user_id,
        name=obj.name,
        description=obj.description,
        visual_properties=obj.visual_properties,
        category=obj.category,
        images=[
            ObjectRefImageResponse(
                id=img.id,
                storage_path=img.storage_path,
                is_primary=img.is_primary,
                sort_order=img.sort_order,
                width=img.width,
                height=img.height,
            )
            for img in (obj.images or [])
        ],
        job_count=len(obj.job_assignments) if obj.job_assignments else 0,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


async def _get_object_ref_or_404(
    object_ref_id: UUID, user_id: UUID, db: AsyncSession
) -> ObjectRef:
    """Fetch an object ref by id + owner, raising 404 if not found."""
    result = await db.execute(
        select(ObjectRef)
        .options(selectinload(ObjectRef.images), selectinload(ObjectRef.job_assignments))
        .where(
            ObjectRef.id == object_ref_id,
            ObjectRef.user_id == user_id,
            ObjectRef.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ObjectRefListResponse)
async def list_objects(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObjectRefListResponse:
    """List current user's non-deleted object refs."""
    # Count query
    count_result = await db.execute(
        select(func.count(ObjectRef.id)).where(
            ObjectRef.user_id == current_user.id,
            ObjectRef.deleted_at.is_(None),
        )
    )
    total = count_result.scalar() or 0

    # Fetch with eager-loaded relations
    result = await db.execute(
        select(ObjectRef)
        .options(selectinload(ObjectRef.images), selectinload(ObjectRef.job_assignments))
        .where(
            ObjectRef.user_id == current_user.id,
            ObjectRef.deleted_at.is_(None),
        )
        .order_by(ObjectRef.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    objects = result.scalars().all()

    return ObjectRefListResponse(
        objects=[_object_ref_to_response(o) for o in objects],
        total=total,
    )


@router.get("/{object_ref_id}", response_model=ObjectRefResponse)
async def get_object_ref(
    object_ref_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObjectRefResponse:
    """Get a single object ref by id."""
    obj = await _get_object_ref_or_404(object_ref_id, current_user.id, db)
    return _object_ref_to_response(obj)


@router.delete("/{object_ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_object_ref(
    object_ref_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete an object ref. Preserves job references."""
    obj = await _get_object_ref_or_404(object_ref_id, current_user.id, db)

    # Log if object has job references
    if obj.job_assignments:
        logger.warning(
            "Soft-deleting object ref %s with %d job references",
            object_ref_id,
            len(obj.job_assignments),
        )

    obj.deleted_at = datetime.utcnow()
    await db.commit()
