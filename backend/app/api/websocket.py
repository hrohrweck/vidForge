import asyncio
import json
from typing import Set

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect

from app.config import get_settings


class ConnectionManager:
    """Manages WebSocket connections for real-time job updates."""

    def __init__(self):
        self.active_connections: dict[str, Set[WebSocket]] = {}
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None

    async def get_redis(self) -> redis.Redis:
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.from_url(settings.redis_url)
        return self._redis

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

    async def subscribe_to_job(self, job_id: str, websocket: WebSocket) -> None:
        r = await self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"job:{job_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        await websocket.send_text(message["data"])
                    except Exception:
                        break
        finally:
            await pubsub.unsubscribe(f"job:{job_id}")


manager = ConnectionManager()
