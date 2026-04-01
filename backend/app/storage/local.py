from __future__ import annotations

from pathlib import Path

from . import StorageBackend


class LocalStorage(StorageBackend):
    """Backward-compatible local storage backend used by legacy imports."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _validate_path(self, path: str) -> Path:
        path = path.replace("\\", "/")
        if path.startswith("/"):
            raise ValueError("Path traversal detected")

        candidate = (self.base_path / path).resolve()
        try:
            candidate.relative_to(self.base_path)
        except ValueError as exc:
            raise ValueError("Path traversal detected") from exc

        return candidate

    async def upload(self, path: str, data: bytes) -> str:
        full_path = self._validate_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        return path

    async def download(self, path: str) -> bytes:
        full_path = self._validate_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not full_path.is_file():
            raise ValueError("Path is not a file")
        return full_path.read_bytes()

    async def delete(self, path: str) -> None:
        full_path = self._validate_path(path)
        if full_path.exists():
            if full_path.is_file():
                full_path.unlink()
            else:
                raise ValueError("Path is not a file")

    async def list_files(self, prefix: str = "") -> list[dict[str, object]]:
        target = self._validate_path(prefix) if prefix else self.base_path
        if not target.exists():
            return []

        files: list[dict[str, object]] = []
        prefix_len = len(str(self.base_path)) + 1
        for entry in target.rglob("*"):
            if not entry.is_file():
                continue
            path = str(entry)
            rel_path = path[prefix_len:] if path.startswith(str(self.base_path) + "/") else path
            files.append(
                {
                    "path": rel_path,
                    "size": entry.stat().st_size,
                    "modified": entry.stat().st_mtime,
                }
            )
        return files

    async def get_url(self, path: str) -> str:
        self._validate_path(path)
        return f"/storage/{path}"
