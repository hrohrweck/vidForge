from __future__ import annotations

import asyncio
import posixpath
from typing import Any

from . import StorageBackend


class SSHStorage(StorageBackend):
    """SSH/SFTP storage backend using async-safe blocking calls."""

    def __init__(
        self,
        host: str,
        user: str,
        key_path: str,
        remote_path: str,
        port: int = 22,
        password: str | None = None,
        known_hosts_path: str | None = None,
    ) -> None:
        import paramiko

        self.host = host
        self.user = user
        self.password = password
        self.key_path = key_path
        self.port = port
        self.remote_path = remote_path.rstrip("/")
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.RejectPolicy())
        if known_hosts_path:
            self._client.load_host_keys(known_hosts_path)
        else:
            self._client.load_system_host_keys()
        self._sftp: Any = None

    def _full_remote_path(self, path: str) -> str:
        if path.startswith("/"):
            path = path.lstrip("/")
        return posixpath.join(self.remote_path, path)

    def _connect(self) -> None:
        if self._sftp is not None:
            return
        self._client.connect(
            hostname=self.host,
            username=self.user,
            key_filename=self.key_path,
            password=self.password,
            port=self.port,
        )
        self._sftp = self._client.open_sftp()

    def _close(self) -> None:
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None

    async def upload(self, path: str, data: bytes) -> None:
        def _upload() -> None:
            try:
                self._connect()
                remote = self._full_remote_path(path)
                with self._sftp.file(remote, "wb") as remote_file:
                    remote_file.write(data)
            finally:
                self._close()

        await asyncio.get_event_loop().run_in_executor(None, _upload)

    async def download(self, path: str) -> bytes:
        def _download() -> bytes:
            try:
                self._connect()
                remote = self._full_remote_path(path)
                with self._sftp.file(remote, "rb") as remote_file:
                    return remote_file.read()
            finally:
                self._close()

        return await asyncio.get_event_loop().run_in_executor(None, _download)

    async def delete(self, path: str) -> None:
        def _delete() -> None:
            try:
                self._connect()
                remote = self._full_remote_path(path)
                self._sftp.remove(remote)
            except FileNotFoundError:
                pass
            finally:
                self._close()

        await asyncio.get_event_loop().run_in_executor(None, _delete)

    async def list_files(self, prefix: str = "") -> list[dict[str, str | int]]:
        def _list() -> list[dict[str, str | int]]:
            try:
                self._connect()
                target = self._full_remote_path(prefix)
                results: list[dict[str, str | int]] = []
                self._walk_files(target, results)
                return results
            finally:
                self._close()

        return await asyncio.get_event_loop().run_in_executor(None, _list)

    def _walk_files(
        self, remote_path: str, results: list[dict[str, str | int]]
    ) -> None:
        for item in self._sftp.listdir_attr(remote_path):
            name = item.filename
            full = posixpath.join(remote_path, name)
            if item.st_mode is not None and item.st_mode & 0o40000:
                self._walk_files(full, results)
                continue
            results.append(
                {
                    "path": full,
                    "size": int(item.st_size),
                    "modified": item.st_mtime,
                }
            )

    async def get_url(self, path: str) -> str:
        return f"/storage/{path}"
