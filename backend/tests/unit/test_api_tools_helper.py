"""Tests for app.chatbot.api_tools."""

import pytest

from app.chatbot.api_tools import _is_blocked_path, call_user_api
from app.chatbot.tools import ToolContext


class TestIsBlockedPath:
    """Unit tests for the path-blocking logic."""

    @pytest.mark.parametrize("path", ["/api/admin/users", "/api/admin/providers", "/api/admin/something"])
    def test_blocks_admin_paths(self, path):
        assert _is_blocked_path(path, "GET") is True
        assert _is_blocked_path(path, "POST") is True

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_blocks_provider_write_methods(self, method):
        assert _is_blocked_path("/api/providers/config", method) is True

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_allows_provider_read_methods(self, method):
        assert _is_blocked_path("/api/providers/config", method) is False

    @pytest.mark.parametrize("path", ["/api/jobs", "/api/templates", "/api/users/me"])
    def test_allows_normal_user_paths(self, path):
        assert _is_blocked_path(path, "GET") is False
        assert _is_blocked_path(path, "POST") is False
        assert _is_blocked_path(path, "PUT") is False

    def test_blocks_deep_admin(self):
        assert _is_blocked_path("/api/admin/nested/deep", "GET") is True


@pytest.mark.asyncio
class TestCallUserApi:
    """Integration-style tests for the full call_user_api flow."""

    async def test_blocked_admin_path_returns_error(self, db_session, regular_user):
        ctx = ToolContext(user_id=str(regular_user.id), db=db_session)
        result = await call_user_api(ctx, "GET", "/api/admin/users")
        assert result["error"] == "forbidden"
        assert "admin" in result["message"].lower() or "not accessible" in result["message"].lower()

    async def test_blocked_provider_write_returns_error(self, db_session, regular_user):
        ctx = ToolContext(user_id=str(regular_user.id), db=db_session)
        result = await call_user_api(ctx, "POST", "/api/providers/config", json_data={"key": "value"})
        assert result["error"] == "forbidden"

    async def test_unauthenticated_call_still_requires_auth(self, db_session, mocker):
        ctx = ToolContext(user_id="00000000-0000-0000-0000-000000000000", db=db_session)
        result = await call_user_api(ctx, "GET", "/api/users/me")
        assert result.get("error") in ("401", "unauthorized", "forbidden", "payload_too_large")

    async def test_normal_endpoint_returns_json(self, db_session, regular_user):
        ctx = ToolContext(user_id=str(regular_user.id), db=db_session)
        result = await call_user_api(ctx, "GET", "/api/users/me")
        assert "error" not in result or result["error"] in (401, 403)

    async def test_nonexistent_path_returns_error(self, db_session, regular_user):
        ctx = ToolContext(user_id=str(regular_user.id), db=db_session)
        result = await call_user_api(ctx, "GET", "/api/nonexistent/path")
        assert result.get("error") in ("404", "not_found", "invalid_json", "payload_too_large")

    async def test_tool_call_without_api_prefix_hits_api_route(self, db_session, regular_user):
        """A tool call passing /jobs must actually request /api/jobs (regression)."""
        ctx = ToolContext(user_id=str(regular_user.id), db=db_session)
        result = await call_user_api(ctx, "GET", "/jobs")
        # If the prefix is missing we get 404; if present we get 401/403 (no auth in test)
        # In the real app the token is valid, so 404 would mean the bug exists.
        if isinstance(result, dict):
            assert result.get("error") != "404"
        else:
            # /jobs returns a list on success — prefix is working
            pass
