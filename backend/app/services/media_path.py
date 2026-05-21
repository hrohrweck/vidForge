"""Media path utilities"""

from pathlib import Path
from uuid import UUID

from app.config import get_settings


def get_media_root() -> Path:
    """Get the root media directory, resolved to absolute path."""
    return Path(get_settings().storage_path).resolve()


def get_user_media_dir(user_id: UUID) -> Path:
    """Get the user-specific media directory."""
    media_root = get_media_root()
    user_dir = media_root / "media" / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_asset_dir(user_id: UUID, asset_id: UUID) -> Path:
    """Get the directory for a specific asset."""
    asset_dir = get_user_media_dir(user_id) / str(asset_id)
    asset_dir.mkdir(parents=True, exist_ok=True)
    return asset_dir


def asset_path(user_id: UUID, asset_id: UUID, filename: str) -> Path:
    """Get the full path for an asset file."""
    return get_asset_dir(user_id, asset_id) / filename


def get_preview_path(user_id: UUID, asset_id: UUID, filename: str = "preview.jpg") -> Path:
    """Get the path for an asset's preview image."""
    return get_asset_dir(user_id, asset_id) / filename


def get_jobs_import_path(job_id: UUID) -> Path:
    """Get the import path for a job's outputs (for auto-import)."""
    return get_media_root() / "Jobs" / str(job_id)


def relative_to_media_root(path: Path) -> Path:
    """Convert an absolute path to be relative to the media root."""
    media_root = get_media_root()
    try:
        return path.relative_to(media_root)
    except ValueError:
        return path


def is_within_media_root(path: Path) -> bool:
    """Check if a path is within the media root."""
    media_root = get_media_root()
    try:
        path.relative_to(media_root)
        return True
    except ValueError:
        return False
