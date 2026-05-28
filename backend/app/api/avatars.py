import logging
import uuid as uuid_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image as PILImage
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import Avatar, AvatarImage, JobAvatar, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AvatarCreate(BaseModel):
    name: str
    gender: Literal["Male", "Female", "Non-binary", "Other"]
    bio: str | None = None
    consistency_strategy: Literal["ip_adapter", "face_swap", "lora", "prompt_only"] = "ip_adapter"

    @field_validator("name")
    @classmethod
    def name_min_length(cls, v: str) -> str:
        if len(v) < 1:
            raise ValueError("name must have at least 1 character")
        return v


class AvatarUpdate(BaseModel):
    name: str | None = None
    gender: Literal["Male", "Female", "Non-binary", "Other"] | None = None
    bio: str | None = None
    consistency_strategy: Literal["ip_adapter", "face_swap", "lora", "prompt_only"] | None = None
    primary_image_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def name_min_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 1:
            raise ValueError("name must have at least 1 character")
        return v


class AvatarImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    storage_path: str
    is_primary: bool
    sort_order: int
    width: int | None = None
    height: int | None = None
    thumbnail_url: str | None = None


class AvatarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    gender: str
    bio: str | None = None
    consistency_strategy: str
    primary_image_id: UUID | None = None
    images: list[AvatarImageResponse] = []
    job_count: int = 0
    lora_training_status: str = "not_trained"
    created_at: datetime
    updated_at: datetime


class AvatarListResponse(BaseModel):
    avatars: list[AvatarResponse]
    total: int


class AvatarImageUploadResponse(BaseModel):
    id: UUID
    storage_path: str
    is_primary: bool
    sort_order: int


class JobAvatarAssignment(BaseModel):
    avatar_id: UUID
    role: str | None = None
    consistency_strategy_override: Literal["ip_adapter", "face_swap", "lora", "prompt_only"] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _avatar_to_response(avatar: Avatar) -> AvatarResponse:
    """Convert ORM Avatar to AvatarResponse, computing job_count from loaded
    relationship."""
    return AvatarResponse(
        id=avatar.id,
        user_id=avatar.user_id,
        name=avatar.name,
        gender=avatar.gender,
        bio=avatar.bio,
        consistency_strategy=avatar.consistency_strategy,
        primary_image_id=avatar.primary_image_id,
        images=[
            AvatarImageResponse(
                id=img.id,
                storage_path=img.storage_path,
                is_primary=img.is_primary,
                sort_order=img.sort_order,
                width=img.width,
                height=img.height,
                thumbnail_url=None,
            )
            for img in avatar.images
        ],
        job_count=len(avatar.job_assignments) if avatar.job_assignments else 0,
        lora_training_status=avatar.lora_training_status,
        created_at=avatar.created_at,
        updated_at=avatar.updated_at,
    )


async def _get_avatar_or_404(
    avatar_id: UUID, user_id: UUID, db: AsyncSession
) -> Avatar:
    """Fetch an avatar by id + owner, raising 404 if not found."""
    result = await db.execute(
        select(Avatar)
        .options(selectinload(Avatar.images), selectinload(Avatar.job_assignments))
        .where(Avatar.id == avatar_id, Avatar.user_id == user_id)
    )
    avatar = result.scalar_one_or_none()
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return avatar


async def _save_image_file(avatar_id: UUID, content: bytes, extension: str) -> str:
    """Save image bytes to disk and return relative storage path."""
    settings = get_settings()
    base_dir = Path(settings.storage_path) / "avatars" / str(avatar_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid_mod.uuid4().hex}.{extension}"
    file_path = base_dir / filename
    file_path.write_bytes(content)
    return f"avatars/{avatar_id}/{filename}"


def _get_image_dimensions(content: bytes) -> tuple[int, int]:
    """Return (width, height) from image bytes."""
    from io import BytesIO

    with PILImage.open(BytesIO(content)) as img:
        return img.size  # (width, height)


async def _get_max_sort_order(db: AsyncSession, avatar_id: UUID) -> int:
    """Return the current max sort_order for avatar images, or 0 if none."""
    result = await db.execute(
        select(func.coalesce(func.max(AvatarImage.sort_order), 0)).where(
            AvatarImage.avatar_id == avatar_id
        )
    )
    return result.scalar() or 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=AvatarListResponse)
async def list_avatars(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvatarListResponse:
    """List current user's non-deleted avatars."""
    # Count query
    count_result = await db.execute(
        select(func.count(Avatar.id)).where(
            Avatar.user_id == current_user.id, Avatar.deleted_at.is_(None)
        )
    )
    total = count_result.scalar() or 0

    # Fetch with eager-loaded relations
    result = await db.execute(
        select(Avatar)
        .options(selectinload(Avatar.images), selectinload(Avatar.job_assignments))
        .where(Avatar.user_id == current_user.id, Avatar.deleted_at.is_(None))
        .order_by(Avatar.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    avatars = result.scalars().all()

    return AvatarListResponse(
        avatars=[_avatar_to_response(a) for a in avatars],
        total=total,
    )


@router.post("", response_model=AvatarResponse, status_code=status.HTTP_201_CREATED)
async def create_avatar(
    data: AvatarCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvatarResponse:
    """Create a new avatar for the current user."""
    avatar = Avatar(
        user_id=current_user.id,
        name=data.name,
        gender=data.gender,
        bio=data.bio,
        consistency_strategy=data.consistency_strategy,
    )
    db.add(avatar)
    await db.commit()
    await db.refresh(avatar, attribute_names=["images", "job_assignments"])
    return _avatar_to_response(avatar)


@router.get("/{avatar_id}", response_model=AvatarResponse)
async def get_avatar(
    avatar_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvatarResponse:
    """Get a single avatar by id."""
    avatar = await _get_avatar_or_404(avatar_id, current_user.id, db)
    return _avatar_to_response(avatar)


@router.put("/{avatar_id}", response_model=AvatarResponse)
async def update_avatar(
    avatar_id: UUID,
    data: AvatarUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvatarResponse:
    """Update an avatar. Only provided fields are changed."""
    avatar = await _get_avatar_or_404(avatar_id, current_user.id, db)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(avatar, field, value)

    avatar.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(avatar, attribute_names=["images", "job_assignments"])
    return _avatar_to_response(avatar)


@router.delete("/{avatar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(
    avatar_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete an avatar. Preserves job references."""
    avatar = await _get_avatar_or_404(avatar_id, current_user.id, db)

    # Log if avatar has job references
    if avatar.job_assignments:
        logger.warning(
            "Soft-deleting avatar %s with %d job references",
            avatar_id,
            len(avatar.job_assignments),
        )

    avatar.deleted_at = datetime.utcnow()
    await db.commit()


@router.post(
    "/{avatar_id}/images",
    response_model=AvatarImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_avatar_image(
    avatar_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvatarImageUploadResponse:
    """Upload an image for an avatar.  JPEG/PNG/WebP, max 10MB."""
    avatar = await _get_avatar_or_404(avatar_id, current_user.id, db)

    # Validate content type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {content_type}. "
            f"Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"File too large: {len(content)} bytes. Maximum: {MAX_IMAGE_SIZE} bytes",
        )

    # Get dimensions
    try:
        width, height = _get_image_dimensions(content)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not read image dimensions: {exc}",
        )

    # Determine file extension
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    extension = ext_map.get(content_type, "bin")

    # Save to disk
    storage_path = await _save_image_file(avatar_id, content, extension)

    # Determine if this should be the primary image
    is_first = len(avatar.images) == 0
    next_sort = await _get_max_sort_order(db, avatar_id) + 1

    # Create DB record
    image = AvatarImage(
        avatar_id=avatar_id,
        storage_path=storage_path,
        is_primary=is_first,
        sort_order=next_sort,
        width=width,
        height=height,
        file_size=len(content),
        content_type=content_type,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)

    # If first image, also set as primary on avatar record
    if is_first:
        avatar.primary_image_id = image.id
        await db.commit()
        await db.refresh(avatar)

    return AvatarImageUploadResponse(
        id=image.id,
        storage_path=image.storage_path,
        is_primary=image.is_primary,
        sort_order=image.sort_order,
    )


@router.delete(
    "/{avatar_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_avatar_image(
    avatar_id: UUID,
    image_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an avatar image. Auto-assigns next primary if needed."""
    avatar = await _get_avatar_or_404(avatar_id, current_user.id, db)

    # Find the image
    result = await db.execute(
        select(AvatarImage).where(
            AvatarImage.id == image_id, AvatarImage.avatar_id == avatar_id
        )
    )
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    was_primary = image.is_primary

    settings = get_settings()
    file_path = Path(settings.storage_path) / image.storage_path
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as exc:
        logger.warning("Could not delete image file %s: %s", file_path, exc)

    await db.delete(image)
    await db.commit()

    # If this was the primary, auto-assign the next image by sort_order
    if was_primary:
        # Re-fetch avatar images (image is already deleted, need fresh load)
        new_result = await db.execute(
            select(AvatarImage)
            .where(AvatarImage.avatar_id == avatar_id)
            .order_by(AvatarImage.sort_order.asc())
            .limit(1)
        )
        next_image = new_result.scalar_one_or_none()
        if next_image:
            avatar.primary_image_id = next_image.id
            next_image.is_primary = True
        else:
            avatar.primary_image_id = None
        await db.commit()


@router.put(
    "/{avatar_id}/images/{image_id}/primary", response_model=AvatarResponse
)
async def set_primary_image(
    avatar_id: UUID,
    image_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvatarResponse:
    """Set an image as the primary for this avatar."""
    avatar = await _get_avatar_or_404(avatar_id, current_user.id, db)

    # Find and validate the target image
    result = await db.execute(
        select(AvatarImage).where(
            AvatarImage.id == image_id, AvatarImage.avatar_id == avatar_id
        )
    )
    target_image = result.scalar_one_or_none()
    if not target_image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Unset all other images
    for img in avatar.images:
        img.is_primary = False

    # Set this one as primary
    target_image.is_primary = True
    avatar.primary_image_id = image_id
    await db.commit()
    await db.refresh(avatar, attribute_names=["images", "job_assignments"])
    return _avatar_to_response(avatar)


@router.post("/{avatar_id}/train-lora", status_code=status.HTTP_202_ACCEPTED)
async def train_avatar_lora(
    avatar_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    avatar = await db.get(Avatar, avatar_id)
    if not avatar or avatar.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Avatar not found")
    if avatar.lora_training_status == "training":
        raise HTTPException(
            status_code=409, detail="LoRA training already in progress"
        )

    from app.workers.tasks import train_avatar_lora as train_lora_task

    train_lora_task.delay(str(avatar_id))
    return {"status": "queued", "avatar_id": str(avatar_id)}


@router.post("/{avatar_id}/generate-poses", status_code=status.HTTP_202_ACCEPTED)
async def generate_avatar_poses(
    avatar_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    avatar = await db.get(Avatar, avatar_id)
    if not avatar or avatar.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Avatar not found")
    if not avatar.primary_image:
        raise HTTPException(status_code=400, detail="Avatar has no primary image")

    import redis.asyncio as aioredis

    settings = get_settings()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        if await r.get(f"avatar:poses:generating:{avatar_id}"):
            raise HTTPException(
                status_code=409, detail="Pose generation already in progress"
            )
    finally:
        await r.close()

    from app.workers.tasks import generate_avatar_poses_task

    generate_avatar_poses_task.delay(str(avatar_id))
    return {"status": "queued", "avatar_id": str(avatar_id)}
