"""
WorkerContext — singleton holding long-lived async resources for a Celery
worker process.  Initialized once via Celery worker_init signal.

Eliminates per-task engine/redis creation by sharing:
  - One SQLAlchemy AsyncEngine with connection pooling
  - One redis.asyncio.Redis client
  - One background event loop (daemon thread)
"""

import asyncio
import logging
from threading import Thread
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


class WorkerContext:
    """Manages the lifecycle of shared async resources for a Celery worker."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[Thread] = None
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._redis: Optional[aioredis.Redis] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background event loop and create shared resources.

        Called from the Celery ``worker_init`` signal — runs once per
        worker process, *before* any tasks are consumed.
        """
        settings = get_settings()

        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        # Create resources on the loop so asyncpg greenlets are in the
        # right thread.
        fut = asyncio.run_coroutine_threadsafe(
            self._create_resources(settings), self._loop
        )
        fut.result(timeout=15)
        logger.info("[WorkerContext] Started — engine and redis ready")

    async def _create_resources(self, settings) -> None:
        self._engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    def stop(self) -> None:
        """Teardown shared resources.

        Called from the Celery ``worker_process_shutdown`` signal.
        """
        if self._loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self._dispose_resources(), self._loop)
        try:
            fut.result(timeout=10)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[WorkerContext] Stopped")

    async def _dispose_resources(self) -> None:
        if self._redis:
            await self._redis.aclose()
        if self._engine:
            await self._engine.dispose()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        assert self._loop is not None, "WorkerContext not started"
        return self._loop

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        assert self._session_factory is not None, "WorkerContext not started"
        return self._session_factory

    @property
    def redis(self) -> aioredis.Redis:
        assert self._redis is not None, "WorkerContext not started"
        return self._redis

    # ------------------------------------------------------------------
    # Coroutine dispatch
    # ------------------------------------------------------------------

    def run(self, coro):
        if self._loop is None or not self._loop.is_running():
            logger.error(
                "[WorkerContext] Event loop is not running (loop=%s). "
                "Attempting to restart context...",
                self._loop,
            )
            try:
                self.stop()
            except Exception:
                pass
            self.start()
            if self._loop is None or not self._loop.is_running():
                raise RuntimeError(
                    "WorkerContext event loop is not running and could not be restarted"
                )
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()


# Module-level singleton — initialized by Celery worker signals.
ctx = WorkerContext()
