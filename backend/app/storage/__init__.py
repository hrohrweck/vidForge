import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


class StorageBackend(ABC):
    @abstractmethod
    async def upload(self, path: str, data: bytes) -> None:
        pass

    @abstractmethod
    async def download(self, path: str) -> bytes:
        pass

    @abstractmethod
    async def delete(self, path: str) -> None:
        pass

    @abstractmethod
    async def list_files(self, prefix: str = "") -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def get_url(self, path: str) -> str:
        pass


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str | None = None):
        self.base_path = Path(base_path or _settings.storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        return self.base_path / path

    async def upload(self, path: str, data: bytes) -> None:
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        logger.debug(f"Uploaded file to {full_path}")

    async def download(self, path: str) -> bytes:
        full_path = self._get_full_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.read_bytes()

    async def delete(self, path: str) -> None:
        full_path = self._get_full_path(path)
        if full_path.exists():
            full_path.unlink()
            logger.debug(f"Deleted file {full_path}")

    async def list_files(self, prefix: str = "") -> list[dict[str, Any]]:
        search_path = self._get_full_path(prefix) if prefix else self.base_path
        if not search_path.exists():
            return []

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(self.base_path)
                stat = item.stat()
                files.append({
                    "path": str(rel_path),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
        return files

    async def get_url(self, path: str) -> str:
        return f"/api/uploads/stream/{path}"


_storage_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    global _storage_backend
    if _storage_backend is None:
        backend = _settings.storage_backend
        if backend == "local":
            _storage_backend = LocalStorage(_settings.storage_path)
        else:
            logger.warning(f"Storage backend '{backend}' not implemented, using local")
            _storage_backend = LocalStorage(_settings.storage_path)
    return _storage_backend