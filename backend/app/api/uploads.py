import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import User
from app.services.video_processor import VideoProcessor
from app.storage import get_storage_backend

router = APIRouter()

ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/mp3", "audio/x-wav", "audio/m4a"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 500 * 1024 * 1024


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    original_filename: str
    content_type: str
    size: int
    path: str
    url: str


def validate_file(file: UploadFile, allowed_types: set[str]) -> None:
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: {allowed_types}",
        )


async def save_upload(file: UploadFile, category: str, user_id: str) -> UploadResponse:
    settings = get_settings()
    storage = get_storage_backend()

    ext = os.path.splitext(file.filename or "file")[1]
    file_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().strftime("%Y/%m/%d")
    storage_path = f"uploads/{category}/{user_id}/{timestamp}/{file_id}{ext}"

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    await storage.upload(storage_path, content)
    url = await storage.get_url(storage_path)

    return UploadResponse(
        file_id=file_id,
        filename=f"{file_id}{ext}",
        original_filename=file.filename or file_id,
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
        path=storage_path,
        url=url,
    )


@router.post("/audio", response_model=UploadResponse)
async def upload_audio(
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
) -> UploadResponse:
    validate_file(file, ALLOWED_AUDIO_TYPES)
    return await save_upload(file, "audio", str(current_user.id))


@router.post("/video", response_model=UploadResponse)
async def upload_video(
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
) -> UploadResponse:
    validate_file(file, ALLOWED_VIDEO_TYPES)
    return await save_upload(file, "video", str(current_user.id))


@router.post("/image", response_model=UploadResponse)
async def upload_image(
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
) -> UploadResponse:
    validate_file(file, ALLOWED_IMAGE_TYPES)
    return await save_upload(file, "image", str(current_user.id))


@router.post("/any", response_model=UploadResponse)
async def upload_any(
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
) -> UploadResponse:
    all_types = ALLOWED_AUDIO_TYPES | ALLOWED_VIDEO_TYPES | ALLOWED_IMAGE_TYPES
    validate_file(file, all_types)

    if file.content_type in ALLOWED_AUDIO_TYPES:
        category = "audio"
    elif file.content_type in ALLOWED_VIDEO_TYPES:
        category = "video"
    else:
        category = "image"

    return await save_upload(file, category, str(current_user.id))


@router.get("/download/{path:path}")
async def download_file(
    path: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    storage = get_storage_backend()

    try:
        content = await storage.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    content_type = "application/octet-stream"
    ext = Path(path).suffix.lower()
    mime_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    content_type = mime_types.get(ext, "application/octet-stream")

    filename = Path(path).name
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )


@router.get("/stream/{path:path}")
async def stream_file(
    path: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    storage = get_storage_backend()

    try:
        content = await storage.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    ext = Path(path).suffix.lower()
    mime_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
    }
    content_type = mime_types.get(ext, "application/octet-stream")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(content)),
        },
    )


class ThumbnailResponse(BaseModel):
    thumbnails: list[str]
    count: int


@router.get("/thumbnail/{path:path}", response_class=Response)
async def get_video_thumbnail(
    path: str,
    timestamp: float = 0.0,
    width: int = 320,
    height: int = 180,
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> Response:
    import tempfile
    import uuid

    storage = get_storage_backend()

    try:
        content = await storage.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Video not found")

    with tempfile.NamedTemporaryFile(suffix=Path(path).suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    thumb_path = tempfile.mktemp(suffix=".jpg")

    try:
        await VideoProcessor.generate_thumbnail(tmp_path, thumb_path, timestamp, width, height)

        if not Path(thumb_path).exists():
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")

        with open(thumb_path, "rb") as f:
            thumb_content = f.read()

        return Response(
            content=thumb_content,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Length": str(len(thumb_content)),
            },
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
        Path(thumb_path).unlink(missing_ok=True)


@router.get("/thumbnails/{path:path}", response_model=ThumbnailResponse)
async def get_video_thumbnails(
    path: str,
    count: int = 5,
    width: int = 320,
    height: int = 180,
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> ThumbnailResponse:
    import tempfile

    storage = get_storage_backend()

    try:
        content = await storage.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Video not found")

    with tempfile.NamedTemporaryFile(suffix=Path(path).suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    thumb_dir = tempfile.mkdtemp()

    try:
        thumbnails = await VideoProcessor.generate_thumbnails(
            tmp_path, thumb_dir, count, width, height
        )

        thumb_urls = []
        for thumb in thumbnails:
            thumb_name = Path(thumb).name
            thumb_urls.append(f"/api/uploads/stream/{path}/../thumbnails/{thumb_name}")

        return ThumbnailResponse(thumbnails=thumb_urls, count=len(thumb_urls))
    finally:
        Path(tmp_path).unlink(missing_ok=True)
        import shutil

        shutil.rmtree(thumb_dir, ignore_errors=True)
