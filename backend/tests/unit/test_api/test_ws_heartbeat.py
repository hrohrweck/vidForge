import asyncio
from unittest.mock import AsyncMock

import pytest

from app.api.ws_heartbeat import PING_MESSAGE, WebSocketHeartbeat


class _MockWebSocket:
    def __init__(self):
        self.send_text = AsyncMock()
        self._closed_event = asyncio.Event()
        self.close = AsyncMock(side_effect=self._on_close)

    async def _on_close(self, *args, **kwargs):
        self._closed_event.set()

    async def wait_closed(self, timeout: float = 1.0):
        await asyncio.wait_for(self._closed_event.wait(), timeout=timeout)


class TestWebSocketHeartbeat:
    @pytest.mark.asyncio
    async def test_sends_ping_at_interval(self):
        websocket = _MockWebSocket()
        heartbeat = WebSocketHeartbeat(
            websocket,
            interval=0.05,
            timeout=0.3,
        )
        heartbeat.start()

        try:
            await asyncio.sleep(0.13)
        finally:
            await heartbeat.stop()

        # Should have received at least two pings within ~0.13s.
        pings = [
            call
            for call in websocket.send_text.await_args_list
            if call.args[0] == PING_MESSAGE
        ]
        assert len(pings) >= 2

    @pytest.mark.asyncio
    async def test_closes_when_peer_is_silent(self):
        websocket = _MockWebSocket()
        heartbeat = WebSocketHeartbeat(
            websocket,
            interval=0.05,
            timeout=0.1,
        )
        heartbeat.start()

        try:
            await websocket.wait_closed()
        except asyncio.TimeoutError:
            pytest.fail("Heartbeat did not close silent WebSocket within timeout")
        finally:
            await heartbeat.stop()

        websocket.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_keeps_connection_alive(self):
        websocket = _MockWebSocket()
        heartbeat = WebSocketHeartbeat(
            websocket,
            interval=0.05,
            timeout=0.15,
        )
        heartbeat.start()

        try:
            # Simulate incoming messages right before each timeout check.
            for _ in range(5):
                await asyncio.sleep(0.08)
                heartbeat.reset()

            websocket.close.assert_not_awaited()
        finally:
            await heartbeat.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self):
        websocket = _MockWebSocket()
        heartbeat = WebSocketHeartbeat(
            websocket,
            interval=0.05,
            timeout=0.3,
        )
        heartbeat.start()
        await heartbeat.stop()
        await heartbeat.stop()

        # Manual stop should only cancel the heartbeat task, not close the
        # WebSocket (the endpoint or the timeout path handles closure).
        websocket.close.assert_not_awaited()
