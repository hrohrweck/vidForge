from __future__ import annotations

import posixpath

from . import StorageBackend


class SSHStorage(StorageBackend):
    """Compatibility wrapper for the SSH storage backend."""

    def __init__(
        self,
        host: str,
        user: str,
        key_path: str,
        remote_path: str,
        port: int = 22,
        password: str | None = None,
    ) -> None:
        import paramiko

        self.host = host
        self.user = user
        self.password = password
        self.key_path = key_path
        self.port = port
        self.remote_path = remote_path.rstrip("/")
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._sftp = None

    def _full_remote_path(self, path: str) -> str:
        if path.startswith("/"):
            path = path.lstrip("/")
        return posixpath.join(self.remote_path, path)

    def _connect(self):
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

    def _close(self):
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None

    async def upload(self, path: str, data: bytes) -> None:
        self._connect()
        try:
            remote = self._full_remote_path(path)
            with self._sftp.file(remote, "wb") as remote_file:
                remote_file.write(data)
        finally:
            self._close()

    async def download(self, path: str) -> bytes:
        self._connect()
        try:
            remote = self._full_remote_path(path)
            with self._sftp.file(remote, "rb") as remote_file:
                return remote_file.read()
        finally:
            self._close()

    async def delete(self, path: str) -> None:
        self._connect()
        try:
            remote = self._full_remote_path(path)
            self._sftp.remove(remote)
        except FileNotFoundError:
            pass
        finally:
            self._close()

    async def list_files(self, prefix: str = "") -> list[dict[str, str | int]]:
        self._connect()
        try:
            target = self._full_remote_path(prefix)
            files: list[dict[str, str | int]] = []
            for entry in self._walk_files(target):
                files.append(entry)
            return files
        finally:
            self._close()

    def _walk_files(self, remote_path: str) -> list[dict[str, str | int]]:
        results: list[dict[str, str | int]] = []
        for item in self._sftp.listdir_attr(remote_path):
            name = item.filename
            full = posixpath.join(remote_path, name)
            if item.st_mode is not None and item.st_mode & 0o40000:
                results.extend(self._walk_files(full))
                continue
            results.append(
                {
                    "path": full,
                    "size": int(item.st_size),
                    "modified": item.st_mtime,
                }
            )
        return results

    async def get_url(self, path: str) -> str:
        return f"/storage/{path}"
