"""WebSocket heartbeat helpers.

Provides a small manager that sends periodic ``{"type": "ping"}`` messages and
closes the connection when the peer stops responding.  This prevents silent
half-open connections caused by idle timeouts in proxies, NAT gateways, or
cloud load balancers.
"""

import asyncio
import json
import logging
import time

from fastapi import WebSocket

logger = logging.getLogger(__name__)

PING_MESSAGE = json.dumps({"type": "ping"})


class WebSocketHeartbeat:
    """Sends pings and enforces a receive timeout for a single WebSocket.

    Usage::

        heartbeat = WebSocketHeartbeat(websocket, interval=20.0, timeout=60.0)
        heartbeat.start()
        try:
            while True:
                data = await websocket.receive_text()
                heartbeat.reset()
                # handle data (pong messages are ignored by the endpoint)
        finally:
            await heartbeat.stop()
    """

    def __init__(
        self,
        websocket: WebSocket,
        interval: float,
        timeout: float,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        self.websocket = websocket
        self.interval = interval
        self.timeout = timeout
        self._send_lock = send_lock
        self._last_seen = time.monotonic()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        """Start the background heartbeat task."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the background heartbeat task."""
        self._closed = True
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def reset(self) -> None:
        """Mark the peer as alive (call whenever a message is received)."""
        self._last_seen = time.monotonic()

    async def _run(self) -> None:
        """Loop: send pings, close if peer is unresponsive."""
        try:
            while True:
                await asyncio.sleep(self.interval)

                if time.monotonic() - self._last_seen > self.timeout:
                    logger.debug("WebSocket heartbeat timeout, closing connection")
                    break

                try:
                    if self._send_lock is not None:
                        async with self._send_lock:
                            await self.websocket.send_text(PING_MESSAGE)
                    else:
                        await self.websocket.send_text(PING_MESSAGE)
                except Exception:
                    logger.debug("Failed to send WebSocket ping, aborting heartbeat")
                    break
        finally:
            await self._close_websocket()

    async def _close_websocket(self) -> None:
        """Close the underlying WebSocket, ignoring errors."""
        if self._closed:
            return
        self._closed = True
        try:
            await self.websocket.close(code=1001)
        except Exception:
            pass
