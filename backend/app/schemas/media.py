"""Media library Pydantic schemas"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    MARKDOWN = "markdown"
    AUDIO = "audio"


class SourceType(str, Enum):
    GENERATED = "generated"
    UPLOADED = "uploaded"


# Folder schemas
class FolderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class FolderCreate(FolderBase):
    parent_id: str | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    parent_id: str | None = None


class FolderResponse(FolderBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime


class FolderTreeResponse(FolderResponse):
    children: list[FolderTreeResponse] = Field(default_factory=list)


# Tag schemas (defined before Asset to avoid forward reference issues)
class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    color: str = Field(..., pattern=r"^[a-fA-F0-9]{6}$")


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    color: str | None = Field(None, pattern=r"^[a-fA-F0-9]{6}$")


class TagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime


# Asset schemas
class AssetListQuery(BaseModel):
    folder_id: str | None = None
    project_id: str | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    file_type: FileType | None = None
    source_type: SourceType | None = None
    tag_ids: list[str] | None = None
    search: str | None = None
    sort_by: Literal["created_at", "name", "size_bytes"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


class AssetResponse(FolderBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    folder_id: str | None
    project_id: str | None = None
    file_path: str
    file_type: FileType
    mime_type: str | None
    size_bytes: int | None
    preview_path: str | None
    source_type: SourceType
    source_job_id: str | None
    asset_metadata: dict | None
    created_at: datetime
    updated_at: datetime
    tags: list[TagResponse] = Field(default_factory=list)


class AssetListResponse(BaseModel):
    assets: list[AssetResponse]
    next_cursor: str | None
    total_count: int | None = None


class AssetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    folder_id: str | None = None
    project_id: str | None = None
    tag_ids: list[str] | None = None


class PreviewFrameRequest(BaseModel):
    timestamp_seconds: float = Field(..., ge=0)


# Bulk operation schemas
class BulkMoveRequest(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1)
    target_folder_id: str | None = None


class BulkDeleteRequest(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1)


class BulkTagRequest(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1)
    tag_ids: list[str] = Field(..., min_length=1)


# Upload response
class UploadResponse(BaseModel):
    assets: list[AssetResponse] = Field(default_factory=list)
    failed: list[dict] = Field(default_factory=list)


# Reference schemas
class ReferenceResponse(BaseModel):
    referrer_asset_id: str
    referenced_asset_id: str
    created_at: datetime
