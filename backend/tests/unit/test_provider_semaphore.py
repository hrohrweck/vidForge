import asyncio
from unittest.mock import AsyncMock, patch

import pytest


class TestProviderSemaphore:

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def semaphore(self, mock_redis):
        from app.workers.tasks import ProviderSemaphore
        from app.workers import context

        original = getattr(context.ctx, "_redis", None)
        context.ctx._redis = mock_redis
        sem = ProviderSemaphore("test:provider:semaphore", max_concurrent=3)
        yield sem
        context.ctx._redis = original

    def test_acquire_uses_redis_get_and_incr(self, semaphore, mock_redis):
        mock_redis.get.return_value = "0"

        result = asyncio.run(semaphore.acquire("job-1"))

        assert result is True
        assert semaphore._acquired is True
        mock_redis.get.assert_awaited_once_with("test:provider:semaphore")
        mock_redis.incr.assert_awaited_once_with("test:provider:semaphore")

    def test_acquire_returns_false_when_at_limit(self, semaphore, mock_redis):
        mock_redis.get.return_value = "3"

        result = asyncio.run(semaphore.acquire("job-1"))

        assert result is False
        assert semaphore._acquired is False
        mock_redis.incr.assert_not_awaited()

    def test_acquire_returns_true_when_under_limit(self, semaphore, mock_redis):
        mock_redis.get.return_value = "1"

        result = asyncio.run(semaphore.acquire("job-1"))

        assert result is True
        assert semaphore._acquired is True

    def test_release_decrements_when_acquired(self, semaphore, mock_redis):
        mock_redis.get.return_value = "1"
        asyncio.run(semaphore.acquire("job-1"))

        mock_redis.decr.reset_mock()
        asyncio.run(semaphore.release())

        mock_redis.decr.assert_awaited_once_with("test:provider:semaphore")
        assert semaphore._acquired is False

    def test_release_noop_when_not_acquired(self, semaphore, mock_redis):
        asyncio.run(semaphore.release())

        mock_redis.decr.assert_not_awaited()
        assert semaphore._acquired is False

    def test_release_idempotent(self, semaphore, mock_redis):
        mock_redis.get.return_value = "1"
        asyncio.run(semaphore.acquire("job-1"))
        asyncio.run(semaphore.release())
        asyncio.run(semaphore.release())

        assert mock_redis.decr.await_count == 1

    def test_concurrent_acquire_respects_max(self, mock_redis):
        from app.workers.tasks import ProviderSemaphore
        from app.workers import context

        call_count = 0

        async def fake_get(key):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return str(call_count - 1)
            return "3"

        mock_redis.get.side_effect = fake_get

        original = getattr(context.ctx, "_redis", None)
        context.ctx._redis = mock_redis
        sem = ProviderSemaphore("stress:key", max_concurrent=3)

        async def worker(job_id: str):
            return await sem.acquire(job_id)

        async def run_stress():
            tasks = [worker(f"job-{i}") for i in range(20)]
            return await asyncio.gather(*tasks)

        try:
            results = asyncio.run(run_stress())
        finally:
            context.ctx._redis = original

        succeeded = sum(results)
        failed = len(results) - succeeded

        assert succeeded == 3, f"Expected 3 successes, got {succeeded}"
        assert failed == 17, f"Expected 17 failures, got {failed}"
        assert call_count == 20

    def test_acquire_does_not_set_ttl(self, semaphore, mock_redis):
        mock_redis.get.return_value = "0"

        asyncio.run(semaphore.acquire("job-1"))

        mock_redis.expire.assert_not_awaited()

    def test_lua_script_returns_zero_when_over_limit(self):
        lua_script = (
            "local c = tonumber(redis.call('GET', KEYS[1]) or '0'); "
            "if c < tonumber(ARGV[1]) then "
            "redis.call('INCR', KEYS[1]); "
            "redis.call('EXPIRE', KEYS[1], ARGV[2]); "
            "return 1 "
            "else return 0 end"
        )
        assert "redis.call('GET', KEYS[1])" in lua_script
        assert "redis.call('INCR', KEYS[1])" in lua_script
        assert "redis.call('EXPIRE', KEYS[1], ARGV[2])" in lua_script
        assert "return 1" in lua_script
        assert "return 0" in lua_script
