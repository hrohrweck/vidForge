from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user, get_current_user_from_bearer_or_cookie
from app.config import get_settings
from app.database import User
from app.storage import get_storage_backend

router = APIRouter()
settings = get_settings()


class StorageConfig(BaseModel):
    backend: str
    config: dict[str, Any] | None = None


class StorageConfigResponse(BaseModel):
    backend: str
    config: dict[str, Any] | None = None


class FileListResponse(BaseModel):
    files: list[dict[str, Any]]


@router.get("/config", response_model=StorageConfigResponse, response_model_exclude_unset=True)
async def get_storage_config(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
) -> dict[str, Any]:
    if not current_user.is_superuser:
        return {"backend": settings.storage_backend}

    return {
        "backend": settings.storage_backend,
        "config": {
            "path": settings.storage_path
            if settings.storage_backend == "local"
            else None,
            "s3_endpoint": settings.s3_endpoint
            if settings.storage_backend == "s3"
            else None,
            "s3_bucket": settings.s3_bucket
            if settings.storage_backend == "s3"
            else None,
        },
    }


@router.get("/files", response_model=FileListResponse)
async def list_files(
    prefix: str = "",
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
) -> dict[str, list]:
    storage = get_storage_backend()
    files = await storage.list_files(f"users/{current_user.id}/{prefix}")
    return {"files": files}


@router.delete("/files/{path:path}")
async def delete_file(
    path: str,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
) -> dict[str, str]:
    storage = get_storage_backend()
    full_path = f"users/{current_user.id}/{path}"
    await storage.delete(full_path)
    return {"status": "deleted"}
