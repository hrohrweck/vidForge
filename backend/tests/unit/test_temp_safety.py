import os
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from httpx import ASGITransport, AsyncClient

from app.api.uploads import MAX_FILE_SIZE, save_upload
from app.main import app
from app.services.disk import ensure_disk_space


class FakeFile:
    def __init__(self, chunks, filename="test.mp4", content_type="video/mp4"):
        self._chunks = chunks
        self.filename = filename
        self.content_type = content_type
        self._idx = 0

    async def read(self, size: int = -1) -> bytes:
        if self._idx >= len(self._chunks):
            return b""
        if size == -1:
            remaining = b"".join(self._chunks[self._idx :])
            self._idx = len(self._chunks)
            return remaining
        chunk = self._chunks[self._idx]
        if len(chunk) > size:
            chunk = chunk[:size]
            self._chunks[self._idx] = self._chunks[self._idx][size:]
        else:
            self._idx += 1
        return chunk


@pytest.fixture
def oversized_chunks():
    chunk_size = 1024 * 1024  # 1 MB
    overshoot = 1
    total = (MAX_FILE_SIZE // chunk_size) + overshoot
    return [b"x" * chunk_size for _ in range(total)]


@pytest.mark.asyncio
async def test_save_upload_rejects_oversized_stream(oversized_chunks):
    """Oversized upload must be rejected early without buffering entire body."""
    storage_mock = MagicMock()
    storage_mock.upload = AsyncMock()
    storage_mock.get_url = AsyncMock(return_value="http://test/url")

    fake_file = FakeFile(oversized_chunks)

    with patch("app.api.uploads.get_storage_backend", return_value=storage_mock):
        with pytest.raises(Exception) as exc_info:
            await save_upload(fake_file, "video", "user-1")  # type: ignore[arg-type]

    assert exc_info.value.status_code == 413
    storage_mock.upload.assert_not_awaited()
    assert fake_file._idx <= len(oversized_chunks)


@pytest.mark.asyncio
async def test_upload_endpoint_413_on_oversized(client, regular_user_token, oversized_chunks):
    """Upload endpoint must return 413 for files exceeding MAX_FILE_SIZE."""
    data = b"x" * len(b"".join(oversized_chunks))
    response = await client.post(
        "/api/uploads/video",
        headers={"Authorization": f"Bearer {regular_user_token}"},
        files={"file": ("big.mp4", BytesIO(data), "video/mp4")},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_thumbnail_temp_files_cleaned_on_ffmpeg_failure(client, regular_user, regular_user_token):
    import app.api.uploads as uploads_module

    storage_mock = MagicMock()
    storage_mock.download = AsyncMock(return_value=b"fake video bytes")

    tmp_files_seen = []
    original_named_temp = tempfile.NamedTemporaryFile
    original_mktemp = tempfile.mktemp

    def tracking_named_temp(*args, **kwargs):
        tmp = original_named_temp(*args, **kwargs)
        tmp_files_seen.append(tmp.name)
        return tmp

    def tracking_mktemp(*args, **kwargs):
        name = original_mktemp(*args, **kwargs)
        tmp_files_seen.append(name)
        return name

    user_id = str(regular_user.id)
    with patch.object(uploads_module, "get_storage_backend", return_value=storage_mock):
        with patch.object(tempfile, "NamedTemporaryFile", side_effect=tracking_named_temp):
            with patch.object(tempfile, "mktemp", side_effect=tracking_mktemp):
                with patch(
                    "app.services.video_processor.VideoProcessor.generate_thumbnail",
                    side_effect=RuntimeError("FFmpeg exploded"),
                ):
                    with pytest.raises(RuntimeError, match="FFmpeg exploded"):
                        await client.get(
                            f"/api/uploads/thumbnail/uploads/video/{user_id}/2024/01/01/fake.mp4",
                            headers={"Authorization": f"Bearer {regular_user_token}"},
                        )

    for path in tmp_files_seen:
        assert not Path(path).exists(), f"temp file was not cleaned: {path}"


@pytest.mark.asyncio
async def test_disk_preflight_raises_when_space_insufficient():
    """ensure_disk_space must raise when available space is below required + headroom."""
    with patch("app.services.disk.shutil.disk_usage") as mock_disk:
        # total=10GB, used=9GB, free=1GB
        mock_disk.return_value = MagicMock(total=10 * 1024**3, used=9 * 1024**3, free=1 * 1024**3)
        with pytest.raises(RuntimeError) as exc_info:
            ensure_disk_space(Path("/tmp"), required_bytes=2 * 1024**3)
        assert "Insufficient disk space" in str(exc_info.value)


@pytest.mark.asyncio
async def test_disk_preflight_passes_when_space_sufficient():
    """ensure_disk_space must succeed when available space covers required + headroom."""
    with patch("app.services.disk.shutil.disk_usage") as mock_disk:
        # total=10GB, used=1GB, free=9GB
        mock_disk.return_value = MagicMock(total=10 * 1024**3, used=1 * 1024**3, free=9 * 1024**3)
        # Should not raise
        ensure_disk_space(Path("/tmp"), required_bytes=1 * 1024**3)
