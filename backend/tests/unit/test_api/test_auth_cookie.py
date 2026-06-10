from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api.auth import TOKEN_COOKIE_NAME


class TestAuthCookie:
    """Tests for httpOnly cookie authentication."""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.zrange = AsyncMock(return_value=[])

        pipe = MagicMock()
        pipe.zremrangebyscore = MagicMock(return_value=None)
        pipe.zcard = MagicMock(return_value=None)
        pipe.zadd = MagicMock(return_value=None)
        pipe.expire = MagicMock(return_value=None)
        pipe.execute = AsyncMock(return_value=[None, 0])
        redis.pipeline = MagicMock(return_value=pipe)

        return redis

    @pytest.mark.asyncio
    async def test_login_sets_httponly_cookie(
        self, client: AsyncClient, regular_user, mock_redis
    ):
        """Login must set the vidforge_token as an httpOnly cookie."""
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/auth/login",
                json={"email": "regular@example.com", "password": "password123"},
            )
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert TOKEN_COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie

    @pytest.mark.asyncio
    async def test_refresh_sets_httponly_cookie(
        self, client: AsyncClient, regular_user_token: str
    ):
        """Refresh endpoint must set (or re-set) the httpOnly cookie."""
        response = await client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert TOKEN_COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie

    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self, client: AsyncClient, regular_user_token: str):
        """Logout must delete the auth cookie."""
        response = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert TOKEN_COOKIE_NAME in set_cookie
        # Max-Age=0 or Expires in the past indicates deletion
        assert "Max-Age=0" in set_cookie or "expires" in set_cookie.lower()

    @pytest.mark.asyncio
    async def test_authenticated_request_with_cookie_only(
        self, client: AsyncClient, regular_user, mock_redis
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            login_resp = await client.post(
                "/api/auth/login",
                json={"email": "regular@example.com", "password": "password123"},
            )
        assert login_resp.status_code == 200
        cookie_header = login_resp.headers.get("set-cookie")
        assert cookie_header
        cookie_value = cookie_header.split(";")[0].strip()

        media_resp = await client.get(
            "/api/media/assets",
            headers={"Cookie": cookie_value},
        )
        assert media_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_token_logged_in_response_body(
        self, client: AsyncClient, regular_user, mock_redis
    ):
        """The login response body still contains the token for scripts/curl,
        but the frontend must not rely on it."""
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/auth/login",
                json={"email": "regular@example.com", "password": "password123"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
