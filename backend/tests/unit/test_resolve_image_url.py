"""Tests for _resolve_image_url in ChatOrchestrator."""

import base64
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.chatbot.service import ChatOrchestrator


@pytest.fixture
def orchestrator():
    return ChatOrchestrator(db=AsyncMock())


def _make_png(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_resolve_api_uploads_stream_url(orchestrator):
    """URLs from /api/uploads/stream/ should be downloaded and base64-encoded."""
    fake_data = b"fake-image-data"
    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(return_value=fake_data)

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/api/uploads/stream/chat-uploads/abc123/foo.png"
        result = await orchestrator._resolve_image_url(url, "image/png")

    assert result.startswith("data:image/png;base64,")
    b64_part = result.split(",")[1]
    assert base64.b64decode(b64_part) == fake_data
    mock_storage.download.assert_awaited_once_with("chat-uploads/abc123/foo.png")


@pytest.mark.asyncio
async def test_resolve_storage_url(orchestrator):
    """Legacy /storage/ URLs should still be base64-encoded."""
    fake_data = b"legacy-data"
    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(return_value=fake_data)

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/storage/images/bar.jpg"
        result = await orchestrator._resolve_image_url(url, None)

    assert result.startswith("data:image/jpeg;base64,")
    b64_part = result.split(",")[1]
    assert base64.b64decode(b64_part) == fake_data
    mock_storage.download.assert_awaited_once_with("images/bar.jpg")


@pytest.mark.asyncio
async def test_resolve_external_http_url(orchestrator):
    """Absolute http/https URLs should be returned as-is."""
    mock_storage = AsyncMock()

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "https://example.com/image.png"
        result = await orchestrator._resolve_image_url(url, "image/png")

    assert result == url
    mock_storage.download.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_download_failure_fallback(orchestrator):
    """If download fails, the original URL should be returned."""
    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(side_effect=Exception("not found"))

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/api/uploads/stream/missing.webp"
        result = await orchestrator._resolve_image_url(url, "image/webp")

    assert result == url


@pytest.mark.asyncio
async def test_small_image_not_resized(orchestrator):
    fake_data = _make_png(100, 100)
    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(return_value=fake_data)

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/api/uploads/stream/chat-uploads/small.png"
        result = await orchestrator._resolve_image_url(url, "image/png")

    assert result.startswith("data:image/png;base64,")
    b64_part = result.split(",")[1]
    decoded = base64.b64decode(b64_part)
    with Image.open(BytesIO(decoded)) as img:
        assert img.size == (100, 100)


@pytest.mark.asyncio
async def test_large_image_downscaled(orchestrator):
    fake_data = _make_png(2000, 2000)
    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(return_value=fake_data)

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/api/uploads/stream/chat-uploads/large.png"
        result = await orchestrator._resolve_image_url(url, "image/png")

    assert result.startswith("data:image/jpeg;base64,")
    b64_part = result.split(",")[1]
    decoded = base64.b64decode(b64_part)
    with Image.open(BytesIO(decoded)) as img:
        assert max(img.size) <= 1568


@pytest.mark.asyncio
async def test_oversized_base64_skipped(orchestrator):
    fake_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)
    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(return_value=fake_data)

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/api/uploads/stream/chat-uploads/huge.bin"
        result = await orchestrator._resolve_image_url(url, "image/png")

    assert result == ""


@pytest.mark.asyncio
async def test_large_png_recompressed_to_jpeg(orchestrator):
    buf = BytesIO()
    img = Image.new("RGB", (800, 800))
    import random
    pixels = [(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
              for _ in range(800 * 800)]
    img.putdata(pixels)
    img.save(buf, format="PNG")
    fake_data = buf.getvalue()

    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(return_value=fake_data)

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/api/uploads/stream/chat-uploads/big.png"
        result = await orchestrator._resolve_image_url(url, "image/png")

    assert result.startswith("data:image/jpeg;base64,")
    b64_part = result.split(",")[1]
    decoded = base64.b64decode(b64_part)
    assert len(decoded) < len(fake_data)


@pytest.mark.asyncio
async def test_resolve_download_failure_fallback(orchestrator):
    """If download fails, the original URL should be returned."""
    mock_storage = AsyncMock()
    mock_storage.download = AsyncMock(side_effect=Exception("not found"))

    with patch("app.chatbot.service.get_storage_backend", return_value=mock_storage):
        url = "/api/uploads/stream/missing.webp"
        result = await orchestrator._resolve_image_url(url, "image/webp")

    assert result == url
