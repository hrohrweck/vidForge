"""Media library API router"""

import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, get_current_user_from_bearer_or_cookie
from app.database import User, get_db
from app.models.media import MediaAsset, MediaAssetReference, MediaAssetTag, MediaFolder, MediaTag
from app.schemas.media import (
    AssetListQuery,
    AssetListResponse,
    AssetResponse,
    AssetUpdate,
    BulkDeleteRequest,
    BulkDownloadRequest,
    BulkMoveRequest,
    BulkTagRequest,
    FileTypeStats,
    FolderCreate,
    FolderResponse,
    FolderTreeResponse,
    FolderUpdate,
    MediaStatsResponse,
    PreviewFrameRequest,
    TagCreate,
    TagResponse,
    TagUpdate,
    UploadResponse,
)
from app.services.app_settings import get_setting
from app.services.media_metadata import probe_audio, probe_image, probe_video
from app.services.media_path import asset_path
from app.services.preview_generator import extract_first_frame

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media"])


# Helper to convert DB model to response
def folder_to_response(folder: MediaFolder) -> FolderResponse:
    return FolderResponse(
        id=str(folder.id),
        user_id=str(folder.user_id),
        parent_id=str(folder.parent_id) if folder.parent_id else None,
        name=folder.name,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def asset_to_response(asset: MediaAsset) -> AssetResponse:
    return AssetResponse(
        id=str(asset.id),
        user_id=str(asset.user_id),
        folder_id=str(asset.folder_id) if asset.folder_id else None,
        name=asset.name,
        file_path=asset.file_path,
        file_type=asset.file_type,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        preview_path=asset.preview_path,
        source_type=asset.source_type,
        source_job_id=str(asset.source_job_id) if asset.source_job_id else None,
        asset_metadata=asset.asset_metadata,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        tags=[tag_to_response(t) for t in asset.tags],
    )


def tag_to_response(tag: MediaTag) -> TagResponse:
    return TagResponse(
        id=str(tag.id),
        user_id=str(tag.user_id),
        name=tag.name,
        color=tag.color,
        created_at=tag.created_at,
    )


# ============== FOLDER ENDPOINTS ==============


async def _get_folder_or_404(db: AsyncSession, folder_id: UUID, user_id: UUID) -> MediaFolder:
    result = await db.execute(
        select(MediaFolder).where(
            MediaFolder.id == folder_id,
            MediaFolder.user_id == user_id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


async def _folder_depth(db: AsyncSession, folder_id: UUID | None, user_id: UUID) -> int:
    depth = 0
    seen: set[UUID] = set()
    current_id = folder_id
    while current_id is not None:
        if current_id in seen:
            raise HTTPException(status_code=400, detail="Folder hierarchy contains a cycle")
        seen.add(current_id)
        folder = await _get_folder_or_404(db, current_id, user_id)
        depth += 1
        current_id = folder.parent_id
    return depth


async def _assert_folder_depth_allowed(
    db: AsyncSession,
    parent_id: UUID | None,
    user_id: UUID,
) -> None:
    max_depth = int(await get_setting(db, "media.max_folder_depth", 3))
    new_folder_depth = await _folder_depth(db, parent_id, user_id) + 1
    if new_folder_depth > max_depth:
        raise HTTPException(
            status_code=400,
            detail=f"Folder depth exceeds maximum allowed depth of {max_depth}",
        )


async def _assert_not_descendant(
    db: AsyncSession,
    folder_id: UUID,
    parent_id: UUID | None,
    user_id: UUID,
) -> None:
    current_id = parent_id
    seen: set[UUID] = set()
    while current_id is not None:
        if current_id == folder_id:
            raise HTTPException(status_code=400, detail="Folder cannot be moved into itself or a descendant")
        if current_id in seen:
            raise HTTPException(status_code=400, detail="Folder hierarchy contains a cycle")
        seen.add(current_id)
        folder = await _get_folder_or_404(db, current_id, user_id)
        current_id = folder.parent_id

@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(
    parent_id: str | None = None,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """List folders for the current user, optionally filtered by parent."""
    query = select(MediaFolder).where(MediaFolder.user_id == current_user.id)
    if parent_id:
        query = query.where(MediaFolder.parent_id == UUID(parent_id))
    else:
        query = query.where(MediaFolder.parent_id.is_(None))

    result = await db.execute(query)
    folders = result.scalars().all()
    return [folder_to_response(f) for f in folders]


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: FolderCreate,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Create a new folder."""
    # Check for duplicate name in same parent
    parent_uuid = UUID(payload.parent_id) if payload.parent_id else None
    await _assert_folder_depth_allowed(db, parent_uuid, current_user.id)

    existing = await db.execute(
        select(MediaFolder).where(
            MediaFolder.user_id == current_user.id,
            MediaFolder.parent_id == parent_uuid,
            MediaFolder.name == payload.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Folder with this name already exists")

    folder = MediaFolder(
        user_id=current_user.id,
        parent_id=parent_uuid,
        name=payload.name,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder_to_response(folder)


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: str,
    payload: FolderUpdate,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Update a folder (rename or move)."""
    result = await db.execute(
        select(MediaFolder).where(
            MediaFolder.id == UUID(folder_id),
            MediaFolder.user_id == current_user.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if payload.name is not None:
        folder.name = payload.name
    if "parent_id" in payload.model_fields_set:
        new_parent_id = UUID(payload.parent_id) if payload.parent_id else None
        await _assert_not_descendant(db, folder.id, new_parent_id, current_user.id)
        await _assert_folder_depth_allowed(db, new_parent_id, current_user.id)
        folder.parent_id = new_parent_id

    await db.commit()
    await db.refresh(folder)
    return folder_to_response(folder)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: str,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Delete a folder. Refused if folder is not empty."""
    result = await db.execute(
        select(MediaFolder).where(
            MediaFolder.id == UUID(folder_id),
            MediaFolder.user_id == current_user.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Check if folder has children (subfolders or assets)
    children_count = await db.execute(
        select(func.count()).where(MediaFolder.parent_id == folder.id)
    )
    if children_count.scalar() > 0:
        raise HTTPException(status_code=409, detail="Folder is not empty")

    assets_count = await db.execute(
        select(func.count()).where(MediaAsset.folder_id == folder.id)
    )
    if assets_count.scalar() > 0:
        raise HTTPException(status_code=409, detail="Folder contains assets")

    await db.delete(folder)
    await db.commit()


@router.get("/folders/tree", response_model=list[FolderTreeResponse])
async def get_folder_tree(
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Get the full folder tree for the current user."""
    result = await db.execute(
        select(MediaFolder).where(MediaFolder.user_id == current_user.id)
    )
    folders = result.scalars().all()

    # Build tree structure using FolderTreeResponse (has children field)
    def folder_to_tree_node(folder: MediaFolder) -> FolderTreeResponse:
        return FolderTreeResponse(
            id=str(folder.id),
            user_id=str(folder.user_id),
            name=folder.name,
            parent_id=str(folder.parent_id) if folder.parent_id else None,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            children=[],
        )
    
    folder_map = {str(f.id): folder_to_tree_node(f) for f in folders}
    root_folders = []

    for folder in folders:
        folder_data = folder_map[str(folder.id)]
        if folder.parent_id and str(folder.parent_id) in folder_map:
            folder_map[str(folder.parent_id)].children.append(folder_data)
        else:
            root_folders.append(folder_data)

    return root_folders


# ============== ASSET ENDPOINTS ==============

@router.get("/assets", response_model=AssetListResponse)
async def list_assets(
    query: Annotated[AssetListQuery, Query()],
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """List assets with cursor pagination and filtering."""
    db_query = select(MediaAsset).where(MediaAsset.user_id == current_user.id)

    # Apply filters
    if query.folder_id:
        db_query = db_query.where(MediaAsset.folder_id == UUID(query.folder_id))
    if query.project_id:
        db_query = db_query.where(MediaAsset.project_id == UUID(query.project_id))
    if query.file_type:
        db_query = db_query.where(MediaAsset.file_type == query.file_type.value)
    if query.source_type:
        db_query = db_query.where(MediaAsset.source_type == query.source_type.value)
    if query.search:
        search_term = f"%{query.search}%"
        db_query = db_query.where(MediaAsset.name.ilike(search_term))

    # Apply sorting
    sort_column = getattr(MediaAsset, query.sort_by, MediaAsset.created_at)
    if query.sort_order == "desc":
        db_query = db_query.order_by(sort_column.desc())
    else:
        db_query = db_query.order_by(sort_column.asc())

    # Apply cursor pagination
    if query.cursor:
        try:
            cursor_date = datetime.fromisoformat(query.cursor)
            if query.sort_order == "desc":
                db_query = db_query.where(MediaAsset.created_at < cursor_date)
            else:
                db_query = db_query.where(MediaAsset.created_at > cursor_date)
        except ValueError:
            pass

    # Limit + 1 to check if there's a next page
    db_query = db_query.limit(query.limit + 1)

    result = await db.execute(db_query)
    assets = result.scalars().all()

    # Check if there's a next page
    next_cursor = None
    if len(assets) > query.limit:
        next_cursor = assets[query.limit - 1].created_at.isoformat()
        assets = assets[:query.limit]

    return AssetListResponse(
        assets=[asset_to_response(a) for a in assets],
        next_cursor=next_cursor,
    )


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: str,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Get a single asset by ID."""
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == UUID(asset_id),
            MediaAsset.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset_to_response(asset)


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Update an asset (rename, move, tags)."""
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == UUID(asset_id),
            MediaAsset.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if payload.name is not None:
        asset.name = payload.name
    if payload.folder_id is not None:
        asset.folder_id = UUID(payload.folder_id) if payload.folder_id else None

    # Update tags if provided
    if payload.tag_ids is not None:
        # Clear existing tags and set new ones
        await db.execute(
            MediaAssetTag.__table__.delete().where(MediaAssetTag.asset_id == asset.id)
        )
        for tag_id in payload.tag_ids:
            db.add(MediaAssetTag(asset_id=asset.id, tag_id=UUID(tag_id)))

    await db.commit()
    await db.refresh(asset)
    return asset_to_response(asset)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: str,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Delete an asset. Refused if referenced in markdown."""
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == UUID(asset_id),
            MediaAsset.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Check if asset is referenced by other assets
    refs_result = await db.execute(
        select(MediaAssetReference).where(
            MediaAssetReference.referenced_asset_id == asset.id
        )
    )
    refs = refs_result.scalars().all()
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Asset is referenced by other assets",
                "referrers": [str(r.referrer_asset_id) for r in refs],
            }
        )

    await db.delete(asset)
    await db.commit()


# ============== TAG ENDPOINTS ==============

@router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """List all tags for the current user."""
    result = await db.execute(
        select(MediaTag).where(MediaTag.user_id == current_user.id)
    )
    tags = result.scalars().all()
    return [tag_to_response(t) for t in tags]


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tag."""
    # Check for duplicate name
    existing = await db.execute(
        select(MediaTag).where(
            MediaTag.user_id == current_user.id,
            MediaTag.name == payload.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tag with this name already exists")

    tag = MediaTag(
        user_id=current_user.id,
        name=payload.name,
        color=payload.color,
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag_to_response(tag)


@router.patch("/tags/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: str,
    payload: TagUpdate,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Update a tag."""
    result = await db.execute(
        select(MediaTag).where(
            MediaTag.id == UUID(tag_id),
            MediaTag.user_id == current_user.id,
        )
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    if payload.name is not None:
        tag.name = payload.name
    if payload.color is not None:
        tag.color = payload.color

    await db.commit()
    await db.refresh(tag)
    return tag_to_response(tag)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tag."""
    result = await db.execute(
        select(MediaTag).where(
            MediaTag.id == UUID(tag_id),
            MediaTag.user_id == current_user.id,
        )
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    await db.delete(tag)
    await db.commit()


# ============== BULK OPERATIONS ==============

@router.post("/assets/bulk/move")
async def bulk_move_assets(
    request: BulkMoveRequest,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Bulk move assets to a different folder."""
    moved = 0
    target_folder_id = UUID(request.target_folder_id) if request.target_folder_id else None

    for asset_id in request.asset_ids:
        result = await db.execute(
            select(MediaAsset).where(
                MediaAsset.id == UUID(asset_id),
                MediaAsset.user_id == current_user.id,
            )
        )
        asset = result.scalar_one_or_none()
        if asset:
            asset.folder_id = target_folder_id
            moved += 1

    await db.commit()
    return {"moved": moved}


@router.post("/assets/bulk/delete")
async def bulk_delete_assets(
    request: BulkDeleteRequest,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Bulk delete assets."""
    deleted = 0

    for asset_id in request.asset_ids:
        result = await db.execute(
            select(MediaAsset).where(
                MediaAsset.id == UUID(asset_id),
                MediaAsset.user_id == current_user.id,
            )
        )
        asset = result.scalar_one_or_none()
        if asset:
            await db.delete(asset)
            deleted += 1

    await db.commit()
    return {"deleted": deleted}


@router.post("/assets/bulk/tag")
async def bulk_tag_assets(
    request: BulkTagRequest,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Bulk tag assets."""
    tagged = 0
    tag_ids = [UUID(tid) for tid in request.tag_ids]

    for asset_id in request.asset_ids:
        result = await db.execute(
            select(MediaAsset).where(
                MediaAsset.id == UUID(asset_id),
                MediaAsset.user_id == current_user.id,
            )
        )
        asset = result.scalar_one_or_none()
        if asset:
            # Add tags (ignore duplicates)
            for tag_id in tag_ids:
                existing = await db.execute(
                    select(MediaAssetTag).where(
                        MediaAssetTag.asset_id == asset.id,
                        MediaAssetTag.tag_id == tag_id,
                    )
                )
                if not existing.scalar_one_or_none():
                    db.add(MediaAssetTag(asset_id=asset.id, tag_id=tag_id))
            tagged += 1

    await db.commit()
    return {"tagged": tagged}


# ============== BULK DOWNLOAD =============

CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming


@router.post("/assets/bulk/download")
async def bulk_download_assets(
    request: BulkDownloadRequest,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Download multiple assets as a ZIP stream."""
    # Fetch assets belonging to current user
    assets = []
    for asset_id in request.asset_ids:
        result = await db.execute(
            select(MediaAsset).where(
                MediaAsset.id == UUID(asset_id),
                MediaAsset.user_id == current_user.id,
            )
        )
        asset = result.scalar_one_or_none()
        if asset:
            assets.append(asset)

    if not assets:
        raise HTTPException(status_code=404, detail="No assets found")

    # Build ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for asset in assets:
            file_path = Path(asset.file_path)
            if not file_path.exists():
                continue
            # Prefix with first 8 chars of asset id to avoid name collisions
            entry_name = f"{asset.id.hex[:8]}_{asset.name}"
            with open(file_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    zip_file.writestr(entry_name, chunk)

    zip_buffer.seek(0)
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=assets.zip"},
    )


# ============== UPLOAD ENDPOINT ==============

@router.post("/assets/upload", response_model=UploadResponse)
async def upload_assets(
    files: list[UploadFile] = File(...),
    folder_id: str | None = Form(None),
    project_id: str | None = Form(None),
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more files as assets."""
    import mimetypes

    uploaded_assets = []
    failed = []

    for file in files:
        try:
            # Determine file type from mime type
            mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"

            if mime_type.startswith("image/"):
                file_type = "image"
            elif mime_type.startswith("video/"):
                file_type = "video"
            elif mime_type.startswith("audio/"):
                file_type = "audio"
            elif mime_type in ("text/markdown", "text/plain"):
                file_type = "markdown"
            else:
                file_type = "image"  # Default fallback

            # Create asset record
            asset = MediaAsset(
                user_id=current_user.id,
                folder_id=UUID(folder_id) if folder_id else None,
                project_id=UUID(project_id) if project_id else None,
                name=file.filename or "unnamed",
                file_path="",  # Will be updated after saving
                file_type=file_type,
                mime_type=mime_type,
                size_bytes=0,  # Will be updated after saving
                source_type="uploaded",
            )
            db.add(asset)
            await db.flush()  # Get asset.id

            # Save file
            file_path = asset_path(current_user.id, asset.id, file.filename or "unnamed")
            content = await file.read()
            file_path.write_bytes(content)

            # Update asset with path and size
            asset.file_path = str(file_path)
            asset.size_bytes = len(content)

            if file_type == "image":
                asset.asset_metadata = probe_image(file_path)
            elif file_type == "video":
                asset.asset_metadata = probe_video(file_path)
            elif file_type == "audio":
                asset.asset_metadata = probe_audio(file_path)

            # Generate preview for videos
            if file_type == "video":
                preview_path = await extract_first_frame(file_path, current_user.id, asset.id)
                if preview_path:
                    asset.preview_path = str(preview_path)

            uploaded_assets.append(asset)

        except Exception as e:
            logger.error(f"Upload failed for {file.filename}: {e}")
            failed.append({"filename": file.filename, "error": str(e)})

    await db.commit()

    # Refresh all uploaded assets
    for asset in uploaded_assets:
        await db.refresh(asset)

    return UploadResponse(
        assets=[asset_to_response(a) for a in uploaded_assets],
        failed=failed,
    )


# ============== PREVIEW ENDPOINT ==============

@router.post("/assets/{asset_id}/preview", response_model=AssetResponse)
async def regenerate_preview(
    asset_id: str,
    request: PreviewFrameRequest,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate preview frame for a video asset."""
    from app.services.preview_generator import extract_preview_frame

    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == UUID(asset_id),
            MediaAsset.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset.file_type != "video":
        raise HTTPException(status_code=400, detail="Preview regeneration only supported for video assets")

    video_path = Path(asset.file_path)
    preview_path = await extract_preview_frame(
        video_path, current_user.id, asset.id,
        timestamp_seconds=request.timestamp_seconds
    )

    if preview_path:
        asset.preview_path = str(preview_path)
        await db.commit()
        await db.refresh(asset)

    return asset_to_response(asset)


# ============== RAW ASSET SERVING ==============


@router.get("/assets/{asset_id}/file")
async def serve_asset_file(
    asset_id: str,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
    download: str = Query(default=None),
):
    """Serve the raw asset file by asset ID.

    Uses cookie-based auth so that browser <img>/<video> tags work
    automatically (they send cookies but not Authorization headers).
    When ?download=1 is present, sets Content-Disposition: attachment.
    """
    from pathlib import Path

    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == UUID(asset_id),
            MediaAsset.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    file_path = Path(asset.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    if download == "1":
        return FileResponse(
            path=file_path,
            media_type=asset.mime_type or "application/octet-stream",
            filename=Path(asset.file_path).name,
            headers={"Content-Disposition": f'attachment; filename="{Path(asset.file_path).name}"'},
        )
    return FileResponse(
        path=file_path,
        media_type=asset.mime_type or "application/octet-stream",
        filename=asset.name,
    )


@router.get("/assets/raw/{asset_path:path}")
async def serve_asset_file_by_path(
    asset_path: str,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Serve raw asset file by storage path (legacy, kept for backward compat)."""
    from pathlib import Path

    # Look up the asset by path to verify ownership
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.file_path.contains(asset_path),
            MediaAsset.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    file_path = Path(asset.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        media_type=asset.mime_type or "application/octet-stream",
        filename=asset.name,
    )


@router.get("/assets/{asset_id}/preview")
async def serve_preview(
    asset_id: str,
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Serve asset preview image."""
    from pathlib import Path

    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == UUID(asset_id),
            MediaAsset.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()

    if not asset or not asset.preview_path:
        raise HTTPException(status_code=404, detail="Preview not found")

    preview_path = Path(asset.preview_path)
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview file not found")

    return FileResponse(
        path=preview_path,
        media_type="image/jpeg",
    )


@router.get("/stats", response_model=MediaStatsResponse)
async def get_media_stats(
    current_user = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            MediaAsset.file_type,
            func.count(MediaAsset.id).label("count"),
            func.coalesce(func.sum(MediaAsset.size_bytes), 0).label("bytes"),
        )
        .where(MediaAsset.user_id == current_user.id)
        .group_by(MediaAsset.file_type)
    )
    rows = result.all()

    by_type: dict[str, FileTypeStats] = {}
    total_bytes = 0
    total_count = 0

    for row in rows:
        ft_stats = FileTypeStats(count=int(row.count), bytes=int(row.bytes))
        file_type_key = row.file_type.value if hasattr(row.file_type, 'value') else str(row.file_type)
        by_type[file_type_key] = ft_stats
        total_bytes += int(row.bytes)
        total_count += int(row.count)

    return MediaStatsResponse(
        count=total_count,
        total_bytes=total_bytes,
        by_type=by_type,
    )


# ============== QUICK GENERATE ==============


class QuickGenerateRequest(BaseModel):
    model_id: str
    prompt: str
    aspect_ratio: str = "1:1"
    duration: int = 5
    negative_prompt: str | None = None
    seed: int | None = None


class QuickGenerateResponse(BaseModel):
    task_id: str
    status: str = "queued"


@router.post("/generate", status_code=202)
async def quick_generate_media(
    req: QuickGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Queue quick media generation. Media appears in library when done."""
    from app.workers.tasks import generate_quick_media

    task = generate_quick_media.delay(
        user_id=str(current_user.id),
        model_id=req.model_id,
        prompt=req.prompt,
        aspect_ratio=req.aspect_ratio,
        duration=req.duration,
        negative_prompt=req.negative_prompt,
        seed=req.seed,
    )
    return QuickGenerateResponse(task_id=task.id)
