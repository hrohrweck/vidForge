from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from httpx import AsyncClient


class TestRateLimiting:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.zrange = AsyncMock(return_value=[])

        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, 0])
        redis.pipeline = MagicMock(return_value=pipe)

        return redis

    @pytest.fixture
    def mock_request(self):
        request = MagicMock(spec=Request)
        request.client.host = "192.168.1.1"
        request.headers = {}
        return request

    def _set_count(self, mock_redis, count):
        pipe = mock_redis.pipeline.return_value
        pipe.execute = AsyncMock(return_value=[None, count])

    @pytest.mark.asyncio
    async def test_login_rate_limit_11th_request_returns_429(
        self, client: AsyncClient, mock_redis
    ):
        self._set_count(mock_redis, 10)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/auth/login",
                json={"email": "test@example.com", "password": "password123"},
            )

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0
        data = response.json()
        assert "rate limit" in data.get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_login_rate_limit_allows_first_10_requests(
        self, client: AsyncClient, mock_redis
    ):
        self._set_count(mock_redis, 9)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/auth/login",
                json={"email": "test@example.com", "password": "wrongpassword"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_register_rate_limit_6th_request_returns_429(
        self, client: AsyncClient, mock_redis
    ):
        self._set_count(mock_redis, 5)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/auth/register",
                json={"email": "newuser@example.com", "password": "password123"},
            )

        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_register_rate_limit_allows_first_5_requests(
        self, client: AsyncClient, mock_redis
    ):
        self._set_count(mock_redis, 4)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/auth/register",
                json={"email": "newuser@example.com", "password": "password123"},
            )

        assert response.status_code != 429

    @pytest.mark.asyncio
    async def test_job_create_rate_limit_31st_request_returns_429(
        self, client: AsyncClient, regular_user_token: str, mock_redis
    ):
        self._set_count(mock_redis, 30)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/jobs",
                json={"title": "Test Job"},
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )

        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_job_create_rate_limit_allows_first_30_requests(
        self, client: AsyncClient, regular_user_token: str, mock_redis
    ):
        self._set_count(mock_redis, 29)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            with patch("app.api.jobs.process_video_job.delay"):
                response = await client.post(
                    "/api/jobs",
                    json={"title": "Test Job"},
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                )

        assert response.status_code != 429

    @pytest.mark.asyncio
    async def test_rate_limit_uses_ip_for_auth_endpoints(self, mock_redis, mock_request):
        from app.dependencies.rate_limit import RateLimiter

        limiter = RateLimiter(times=10, seconds=60)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            key = await limiter._get_key(mock_request, user_id=None)
            assert "192.168.1.1" in key

    @pytest.mark.asyncio
    async def test_rate_limit_uses_user_id_for_job_endpoints(self, mock_redis, mock_request):
        from app.dependencies.rate_limit import RateLimiter

        limiter = RateLimiter(times=30, seconds=60)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            key = await limiter._get_key(mock_request, user_id="user-123")
            assert "user-123" in key
            assert "192.168.1.1" not in key

    @pytest.mark.asyncio
    async def test_rate_limit_sliding_window_logic(self, mock_redis):
        from app.dependencies.rate_limit import RateLimiter

        limiter = RateLimiter(times=5, seconds=60)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            self._set_count(mock_redis, 4)
            is_allowed = await limiter.is_allowed("test:key")
            assert is_allowed is True

            self._set_count(mock_redis, 5)
            is_allowed = await limiter.is_allowed("test:key")
            assert is_allowed is False

    @pytest.mark.asyncio
    async def test_rate_limit_retry_after_calculation(self, mock_redis):
        import time

        from app.dependencies.rate_limit import RateLimiter

        limiter = RateLimiter(times=5, seconds=60)
        now = time.time()

        mock_redis.zrange.return_value = [(b"member", now - 30)]

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            retry_after = await limiter.get_retry_after("test:key")
            assert 25 <= retry_after <= 35

    @pytest.mark.asyncio
    async def test_rate_limit_records_request(self, mock_redis):
        from app.dependencies.rate_limit import RateLimiter

        limiter = RateLimiter(times=10, seconds=60)
        self._set_count(mock_redis, 0)

        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            await limiter.is_allowed("test:key")

            pipe = mock_redis.pipeline.return_value
            pipe.zadd.assert_called_once()
            pipe.expire.assert_called_once()
