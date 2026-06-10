"""Tests for the worker context and refactored task infrastructure."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWorkerContext:
    """Unit tests for WorkerContext lifecycle."""

    def test_start_creates_loop_and_resources(self):
        from app.workers.context import WorkerContext

        ctx = WorkerContext()

        mock_engine = MagicMock()
        mock_session_factory = MagicMock()
        mock_redis = AsyncMock()

        with patch("app.workers.context.create_async_engine", return_value=mock_engine), \
             patch("app.workers.context.async_sessionmaker", return_value=mock_session_factory), \
             patch("app.workers.context.aioredis.from_url", return_value=mock_redis):
            ctx.start()

        assert ctx._loop is not None
        assert ctx._thread is not None
        assert ctx._thread.daemon is True
        assert ctx.session_factory is mock_session_factory
        assert ctx.redis is mock_redis

        ctx.stop()

    def test_stop_disposes_resources(self):
        from app.workers.context import WorkerContext

        ctx = WorkerContext()
        mock_engine = MagicMock()
        mock_redis = AsyncMock()

        with patch("app.workers.context.create_async_engine", return_value=mock_engine), \
             patch("app.workers.context.async_sessionmaker", return_value=MagicMock()), \
             patch("app.workers.context.aioredis.from_url", return_value=mock_redis):
            ctx.start()
            ctx.stop()

        # After stop, loop should be cleaned up
        assert ctx._loop is not None  # still exists but stopped
        # Thread should have joined
        assert not ctx._thread.is_alive()

    def test_run_executes_coroutine(self):
        from app.workers.context import WorkerContext

        ctx = WorkerContext()

        with patch("app.workers.context.create_async_engine", return_value=MagicMock()), \
             patch("app.workers.context.async_sessionmaker", return_value=MagicMock()), \
             patch("app.workers.context.aioredis.from_url", return_value=AsyncMock()):
            ctx.start()

        result = ctx.run(_helper_add(2, 3))
        assert result == 5

        ctx.stop()

    def test_run_coroutine_threadsafe_reuse(self):
        """Verify that multiple ctx.run() calls reuse the same loop."""
        from app.workers.context import WorkerContext

        ctx = WorkerContext()

        with patch("app.workers.context.create_async_engine", return_value=MagicMock()), \
             patch("app.workers.context.async_sessionmaker", return_value=MagicMock()), \
             patch("app.workers.context.aioredis.from_url", return_value=AsyncMock()):
            ctx.start()

        loop_id = id(ctx.loop)
        ctx.run(_helper_nop())
        assert id(ctx.loop) == loop_id
        ctx.run(_helper_nop())
        assert id(ctx.loop) == loop_id

        ctx.stop()

    def test_accessors_raise_before_start(self):
        from app.workers.context import WorkerContext

        ctx = WorkerContext()
        with pytest.raises(AssertionError, match="not started"):
            _ = ctx.loop
        with pytest.raises(AssertionError, match="not started"):
            _ = ctx.session_factory
        with pytest.raises(AssertionError, match="not started"):
            _ = ctx.redis


class TestBroadcastUpdate:
    """Verify broadcast_update uses the shared redis client."""

    @pytest.mark.asyncio
    async def test_publishes_to_redis(self):
        from app.workers.context import WorkerContext

        ctx = WorkerContext()
        mock_redis = AsyncMock()

        with patch("app.workers.context.create_async_engine", return_value=MagicMock()), \
             patch("app.workers.context.async_sessionmaker", return_value=MagicMock()), \
             patch("app.workers.context.aioredis.from_url", return_value=mock_redis):
            ctx.start()

        with patch("app.workers.tasks.ctx", ctx):
            from app.workers.tasks import broadcast_update
            await broadcast_update("test-job", {"status": "processing"})

        mock_redis.publish.assert_awaited_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "job:test-job"
        assert '"status": "processing"' in call_args[0][1]

        ctx.stop()


class TestProviderSemaphore:

    @pytest.mark.asyncio
    async def test_acquire_uses_redis_get_and_incr(self):
        from app.workers.context import WorkerContext
        from app.workers.tasks import ProviderSemaphore

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"0")

        ctx = WorkerContext()
        with patch("app.workers.context.create_async_engine", return_value=MagicMock()), \
             patch("app.workers.context.async_sessionmaker", return_value=MagicMock()), \
             patch("app.workers.context.aioredis.from_url", return_value=mock_redis):
            ctx.start()

        with patch("app.workers.tasks.ctx", ctx):
            sem = ProviderSemaphore(key="test:sem", max_concurrent=2)
            acquired = await sem.acquire("job-1")

        assert acquired is True
        mock_redis.get.assert_awaited_once_with("test:sem")
        mock_redis.incr.assert_awaited_once_with("test:sem")

        ctx.stop()

    @pytest.mark.asyncio
    async def test_release_decrements_redis(self):
        from app.workers.context import WorkerContext
        from app.workers.tasks import ProviderSemaphore

        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=1)
        mock_redis.get = AsyncMock(return_value=b"1")
        mock_redis.decr = AsyncMock(return_value=0)

        ctx = WorkerContext()
        with patch("app.workers.context.create_async_engine", return_value=MagicMock()), \
             patch("app.workers.context.async_sessionmaker", return_value=MagicMock()), \
              patch("app.workers.context.aioredis.from_url", return_value=mock_redis):
            ctx.start()

        with patch("app.workers.tasks.ctx", ctx):
            sem = ProviderSemaphore(key="test:sem", max_concurrent=2)
            await sem.acquire("job-1")
            await sem.release()

        mock_redis.decr.assert_awaited_once_with("test:sem")

        ctx.stop()


# -- Helper coroutines --------------------------------------------------

async def _helper_add(a, b):
    return a + b


async def _helper_nop():
    pass
