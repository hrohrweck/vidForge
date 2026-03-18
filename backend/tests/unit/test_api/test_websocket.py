import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.api.websocket import ConnectionManager


class TestConnectionManager:
    def test_init(self):
        manager = ConnectionManager()
        assert manager.active_connections == {}
        assert manager._redis is None

    def test_disconnect_removes_connection(self):
        manager = ConnectionManager()
        websocket = MagicMock()
        job_id = "test-job-id"

        manager.active_connections[job_id] = {websocket}
        manager.disconnect(websocket, job_id)

        assert job_id not in manager.active_connections

    def test_disconnect_removes_empty_job_set(self):
        manager = ConnectionManager()
        websocket = MagicMock()
        job_id = "test-job-id"

        manager.active_connections[job_id] = {websocket}
        manager.disconnect(websocket, job_id)

        assert job_id not in manager.active_connections

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self):
        manager = ConnectionManager()
        websocket = AsyncMock()
        job_id = "test-job-id"

        await manager.connect(websocket, job_id)

        websocket.accept.assert_called_once()
        assert job_id in manager.active_connections
        assert websocket in manager.active_connections[job_id]

    @pytest.mark.asyncio
    async def test_connect_multiple_websockets_same_job(self):
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        job_id = "test-job-id"

        await manager.connect(ws1, job_id)
        await manager.connect(ws2, job_id)

        assert len(manager.active_connections[job_id]) == 2

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_connections(self):
        manager = ConnectionManager()
        websocket = AsyncMock()
        job_id = "test-job-id"

        await manager.connect(websocket, job_id)

        with patch.object(manager, "get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()

            await manager._broadcast(job_id, "test message")

            websocket.send_text.assert_called_once_with("test message")

    @pytest.mark.asyncio
    async def test_broadcast_removes_disconnected_websockets(self):
        manager = ConnectionManager()
        websocket = AsyncMock()
        websocket.send_text.side_effect = Exception("Connection lost")
        job_id = "test-job-id"

        await manager.connect(websocket, job_id)

        with patch.object(manager, "get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()

            await manager._broadcast(job_id, "test message")

            assert job_id not in manager.active_connections

    @pytest.mark.asyncio
    async def test_send_progress_sends_correct_message(self):
        manager = ConnectionManager()
        websocket = AsyncMock()
        job_id = "test-job-id"

        await manager.connect(websocket, job_id)

        with patch.object(manager, "get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()

            await manager.send_progress(job_id, 50, "processing")

            expected = json.dumps(
                {"type": "progress", "job_id": job_id, "progress": 50, "status": "processing"}
            )
            websocket.send_text.assert_called_once_with(expected)

    @pytest.mark.asyncio
    async def test_send_completion_sends_correct_message(self):
        manager = ConnectionManager()
        websocket = AsyncMock()
        job_id = "test-job-id"

        await manager.connect(websocket, job_id)

        with patch.object(manager, "get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()

            await manager.send_completion(job_id, "/output/video.mp4", "/preview/video.mp4")

            call_args = websocket.send_text.call_args[0][0]
            data = json.loads(call_args)
            assert data["type"] == "completed"
            assert data["job_id"] == job_id
            assert data["output_path"] == "/output/video.mp4"
            assert data["preview_path"] == "/preview/video.mp4"

    @pytest.mark.asyncio
    async def test_send_error_sends_correct_message(self):
        manager = ConnectionManager()
        websocket = AsyncMock()
        job_id = "test-job-id"

        await manager.connect(websocket, job_id)

        with patch.object(manager, "get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()

            await manager.send_error(job_id, "Something went wrong")

            call_args = websocket.send_text.call_args[0][0]
            data = json.loads(call_args)
            assert data["type"] == "error"
            assert data["job_id"] == job_id
            assert data["error"] == "Something went wrong"
