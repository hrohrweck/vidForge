import logging
import uuid as uuid_mod
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image as PILImage
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user, get_current_user_from_bearer_or_cookie
from app.config import get_settings
from app.database import ObjectRef, ObjectRefImage, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ObjectRefImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

    id: UUID
    storage_path: str
    is_primary: bool
    sort_order: int
    width: int | None = None
    height: int | None = None


class ObjectRefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

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


class ObjectRefCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    description: str | None = None
    category: str | None = None
    visual_properties: dict | None = None


class ObjectRefImageUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

    id: UUID
    storage_path: str
    is_primary: bool
    sort_order: int
    width: int | None = None
    height: int | None = None


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


async def _get_object_ref_or_404(object_ref_id: UUID, user_id: UUID, db: AsyncSession) -> ObjectRef:
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


def _get_image_dimensions(content: bytes) -> tuple[int, int]:
    from io import BytesIO

    with PILImage.open(BytesIO(content)) as img:
        return img.size


async def _save_image_file(object_ref_id: UUID, content: bytes, extension: str) -> str:
    settings = get_settings()
    base_dir = Path(settings.storage_path) / "objects" / str(object_ref_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid_mod.uuid4().hex}.{extension}"
    file_path = base_dir / filename
    file_path.write_bytes(content)
    return f"objects/{object_ref_id}/{filename}"


async def _get_max_sort_order(db: AsyncSession, object_ref_id: UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(ObjectRefImage.sort_order), 0)).where(
            ObjectRefImage.object_ref_id == object_ref_id
        )
    )
    return result.scalar() or 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ObjectRefListResponse)
async def list_objects(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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


@router.post("", response_model=ObjectRefResponse, status_code=status.HTTP_201_CREATED)
async def create_object_ref(
    data: ObjectRefCreate,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ObjectRefResponse:
    obj = ObjectRef(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        category=data.category,
        visual_properties=data.visual_properties,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj, attribute_names=["images", "job_assignments"])
    return _object_ref_to_response(obj)


@router.get("/{object_ref_id}", response_model=ObjectRefResponse)
async def get_object_ref(
    object_ref_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ObjectRefResponse:
    """Get a single object ref by id."""
    obj = await _get_object_ref_or_404(object_ref_id, current_user.id, db)
    return _object_ref_to_response(obj)


@router.post(
    "/{object_ref_id}/images",
    response_model=ObjectRefImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_object_ref_image(
    object_ref_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ObjectRefImageUploadResponse:
    obj = await _get_object_ref_or_404(object_ref_id, current_user.id, db)

    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {content_type}. Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"File too large: {len(content)} bytes. Maximum: {MAX_IMAGE_SIZE} bytes",
        )

    try:
        width, height = _get_image_dimensions(content)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not read image dimensions: {exc}",
        )

    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    extension = ext_map.get(content_type, "bin")

    storage_path = await _save_image_file(object_ref_id, content, extension)

    is_first = len(obj.images) == 0
    next_sort = await _get_max_sort_order(db, object_ref_id) + 1

    image = ObjectRefImage(
        object_ref_id=object_ref_id,
        storage_path=storage_path,
        is_primary=is_first,
        sort_order=next_sort,
        width=width,
        height=height,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)

    return ObjectRefImageUploadResponse(
        id=image.id,
        storage_path=image.storage_path,
        is_primary=image.is_primary,
        sort_order=image.sort_order,
        width=image.width,
        height=image.height,
    )


@router.delete("/{object_ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_object_ref(
    object_ref_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete an object ref. Preserves job references."""
    obj = await _get_object_ref_or_404(object_ref_id, current_user.id, db)

    if obj.job_assignments:
        logger.warning(
            "Soft-deleting object ref %s with %d job references",
            object_ref_id,
            len(obj.job_assignments),
        )

    obj.deleted_at = datetime.utcnow()
    await db.commit()
