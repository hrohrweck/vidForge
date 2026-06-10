import pytest
from pathlib import Path
from app.storage.local import LocalStorage


class TestLocalStorageTraversal:
    """Test that LocalStorage rejects path traversal attempts."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> LocalStorage:
        return LocalStorage(str(tmp_path))

    @pytest.mark.asyncio
    async def test_upload_rejects_traversal(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            await storage.upload("../../etc/passwd", b"evil")

    @pytest.mark.asyncio
    async def test_download_rejects_traversal(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            await storage.download("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_delete_rejects_traversal(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            await storage.delete("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_get_url_rejects_traversal(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            await storage.get_url("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_list_files_rejects_traversal(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            await storage.list_files("../../etc")

    @pytest.mark.asyncio
    async def test_normal_relative_path_works(self, storage: LocalStorage, tmp_path: Path) -> None:
        await storage.upload("foo/bar.txt", b"hello")
        data = await storage.download("foo/bar.txt")
        assert data == b"hello"

    @pytest.mark.asyncio
    async def test_absolute_path_rejected(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            await storage.upload("/etc/passwd", b"evil")

    @pytest.mark.asyncio
    async def test_backslash_traversal_rejected(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            await storage.upload("..\\..\\etc\\passwd", b"evil")
