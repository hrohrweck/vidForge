import logging
from abc import ABC, abstractmethod
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


_storage_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    global _storage_backend
    if _storage_backend is None:
        backend = _settings.storage_backend
        if backend == "local":
            from .local import LocalStorage

            _storage_backend = LocalStorage(_settings.storage_path)
        elif backend == "s3":
            from .s3 import S3Storage

            _storage_backend = S3Storage(
                endpoint=_settings.s3_endpoint,
                access_key=_settings.s3_access_key,
                secret_key=_settings.s3_secret_key,
                bucket=_settings.s3_bucket,
                region=_settings.s3_region,
            )
        elif backend == "ssh":
            from .ssh import SSHStorage

            _storage_backend = SSHStorage(
                host=_settings.ssh_host,
                user=_settings.ssh_user,
                key_path=_settings.ssh_key_path,
                remote_path=_settings.ssh_remote_path,
                known_hosts_path=_settings.ssh_known_hosts_path,
            )
        else:
            from .local import LocalStorage

            logger.warning(f"Storage backend '{backend}' not implemented, using local")
            _storage_backend = LocalStorage(_settings.storage_path)
    return _storage_backend
