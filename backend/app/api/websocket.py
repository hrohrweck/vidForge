import asyncio
import json
import logging
from typing import Set

import redis.asyncio as redis
from fastapi import WebSocket

from app.config import get_settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time job updates."""

    def __init__(self):
        self.active_connections: dict[str, Set[WebSocket]] = {}
        # Notification connections: per-user and admin-wide
        self.user_connections: dict[str, Set[WebSocket]] = {}
        self.admin_connections: Set[WebSocket] = set()
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None

    async def get_redis(self) -> redis.Redis:
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.from_url(settings.redis_url)
        return self._redis

    # ------------------------------------------------------------------
    # Job-scoped connections (existing)
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

    async def send_progress(self, job_id: str, progress: int, status: str) -> None:
        message = json.dumps(
            {
                "type": "progress",
                "job_id": job_id,
                "progress": progress,
                "status": status,
            }
        )
        await self._broadcast(job_id, message)

    async def send_completion(
        self, job_id: str, output_path: str | None, preview_path: str | None
    ) -> None:
        message = json.dumps(
            {
                "type": "completed",
                "job_id": job_id,
                "output_path": output_path,
                "preview_path": preview_path,
            }
        )
        await self._broadcast(job_id, message)

    async def send_error(self, job_id: str, error_message: str) -> None:
        message = json.dumps(
            {
                "type": "error",
                "job_id": job_id,
                "error": error_message,
            }
        )
        await self._broadcast(job_id, message)

    async def _broadcast(self, job_id: str, message: str) -> None:
        r = await self.get_redis()
        await r.publish(f"job:{job_id}", message)

        if job_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)
            for conn in disconnected:
                self.disconnect(conn, job_id)

    async def broadcast_chat_message(self, conversation_id: str, message_id: str) -> None:
        payload = json.dumps(
            {
                "type": "chat_message_appended",
                "conversation_id": conversation_id,
                "message_id": message_id,
            }
        )
        r = await self.get_redis()
        await r.publish(f"chat:{conversation_id}", payload)

    async def subscribe_to_job(
        self,
        job_id: str,
        websocket: WebSocket,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        r = await self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"job:{job_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        if send_lock is not None:
                            async with send_lock:
                                await websocket.send_text(message["data"])
                        else:
                            await websocket.send_text(message["data"])
                    except Exception:
                        break
        finally:
            await pubsub.unsubscribe(f"job:{job_id}")

    async def subscribe_to_chat(
        self,
        conversation_id: str,
        websocket: WebSocket,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        r = await self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"chat:{conversation_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        if send_lock is not None:
                            async with send_lock:
                                await websocket.send_text(message["data"])
                        else:
                            await websocket.send_text(message["data"])
                    except Exception:
                        break
        finally:
            await pubsub.unsubscribe(f"chat:{conversation_id}")

    # ------------------------------------------------------------------
    # User / admin notification connections
    # ------------------------------------------------------------------

    MAX_CONNECTIONS_PER_USER = 10

    async def connect_user(self, websocket: WebSocket, user_id: str) -> None:
        """Register a WebSocket for user-level notification delivery.

        Caps per-user connections at MAX_CONNECTIONS_PER_USER; oldest
        connection is closed with code 1008 when exceeded.
        """
        await websocket.accept()
        conns = self.user_connections.setdefault(user_id, set())
        if len(conns) >= self.MAX_CONNECTIONS_PER_USER:
            oldest = next(iter(conns))
            try:
                await oldest.close(code=1008, reason="Connection limit exceeded")
            except Exception:
                pass
            conns.discard(oldest)
        conns.add(websocket)

    def disconnect_user(self, websocket: WebSocket, user_id: str) -> None:
        """Remove a WebSocket from user-level notification delivery."""
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def connect_admin(self, websocket: WebSocket) -> None:
        """Register a WebSocket for admin-level notification delivery."""
        await websocket.accept()
        self.admin_connections.add(websocket)

    def disconnect_admin(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from admin-level notification delivery."""
        self.admin_connections.discard(websocket)

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        """Send a notification payload to all connections for *user_id*.

        Publishes to Redis ``notifications:user:{user_id}`` and also pushes
        directly to any in-process connections.
        """
        message = json.dumps(payload)
        try:
            r = await self.get_redis()
            await r.publish(f"notifications:user:{user_id}", message)
        except Exception:
            logger.warning(
                "Failed to publish notification to Redis for user %s",
                user_id,
                exc_info=True,
            )

        if user_id in self.user_connections:
            disconnected = set()
            for connection in self.user_connections[user_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)
            for conn in disconnected:
                self.disconnect_user(conn, user_id)

    async def send_to_admins(self, payload: dict) -> None:
        """Send a notification payload to all admin connections.

        Publishes to Redis ``notifications:admin`` and also pushes directly
        to any in-process connections.
        """
        message = json.dumps(payload)
        try:
            r = await self.get_redis()
            await r.publish("notifications:admin", message)
        except Exception:
            logger.warning(
                "Failed to publish admin notification to Redis",
                exc_info=True,
            )

        disconnected = set()
        for connection in self.admin_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.disconnect_admin(conn)

    async def subscribe_to_user_notifications(
        self,
        user_id: str,
        websocket: WebSocket,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        """Forward Redis ``notifications:user:{user_id}`` messages to *websocket*."""
        r = await self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"notifications:user:{user_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        if send_lock is not None:
                            async with send_lock:
                                await websocket.send_text(message["data"])
                        else:
                            await websocket.send_text(message["data"])
                    except Exception:
                        break
        finally:
            await pubsub.unsubscribe(f"notifications:user:{user_id}")

    async def subscribe_to_admin_notifications(
        self,
        websocket: WebSocket,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        """Forward Redis ``notifications:admin`` messages to *websocket*."""
        r = await self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe("notifications:admin")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        if send_lock is not None:
                            async with send_lock:
                                await websocket.send_text(message["data"])
                        else:
                            await websocket.send_text(message["data"])
                    except Exception:
                        break
        finally:
            await pubsub.unsubscribe("notifications:admin")

    async def get_next_media_seq(self, user_id: str) -> int:
        r = await self.get_redis()
        return await r.incr(f"media:seq:{user_id}")

    async def broadcast_media_event(self, user_id: str, payload: dict) -> None:
        message = json.dumps(payload)
        try:
            r = await self.get_redis()
            await r.publish(f"media:user:{user_id}", message)
        except Exception:
            logger.warning(
                "Failed to publish media event to Redis for user %s",
                user_id,
                exc_info=True,
            )

        if user_id in self.user_connections:
            disconnected = set()
            for connection in self.user_connections[user_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)
            for conn in disconnected:
                self.disconnect_user(conn, user_id)

    async def subscribe_to_media_events(
        self,
        user_id: str,
        websocket: WebSocket,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        r = await self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"media:user:{user_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        if send_lock is not None:
                            async with send_lock:
                                await websocket.send_text(message["data"])
                        else:
                            await websocket.send_text(message["data"])
                    except Exception:
                        break
        finally:
            await pubsub.unsubscribe(f"media:user:{user_id}")


manager = ConnectionManager()
