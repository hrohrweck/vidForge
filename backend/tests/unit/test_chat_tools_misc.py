"""Tests for chatbot tools: styles, avatars, audio, uploads, user settings, templates."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.chatbot.tools import ToolContext, create_builtin_registry, dispatch


@pytest.fixture
def registry():
    """Fresh built-in registry for each test."""
    return create_builtin_registry()


@pytest.fixture
def tool_context():
    """ToolContext with a dummy user_id."""

    def _make(db_session=None):
        return ToolContext(user_id=str(uuid4()), db=db_session)

    return _make


class TestToolRegistrationCount:
    """Ensure all new tools are registered."""

    def test_registry_has_expected_tools(self, registry):
        """All T11 tools should be present in the registry."""
        expected = {
            # Templates
            "get_template",
            "create_template",
            "update_template",
            "delete_template",
            # Styles
            "get_style",
            "create_style",
            "update_style",
            "delete_style",
            # Avatars
            "list_avatars",
            "get_avatar",
            "create_avatar",
            "update_avatar",
            "delete_avatar",
            # Audio
            "get_audio_status",
            "generate_music",
            # Uploads
            "upload_image_url",
            "upload_video_url",
            "upload_audio_url",
            # User settings
            "get_user_settings",
            "update_user_settings",
        }
        for name in expected:
            assert registry.get(name) is not None, f"Tool '{name}' not registered"
            assert callable(registry.get(name).handler)


class TestTemplateTools:
    """Happy-path tests for template tools via mocked call_user_api."""

    @pytest.mark.asyncio
    async def test_get_template(self, registry, tool_context):
        """get_template calls GET /templates/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "tmpl-1", "name": "Test"},
        ) as mock_call:
            result = await dispatch("get_template", {"id": "tmpl-1"}, ctx, registry)
            assert result["id"] == "tmpl-1"
            mock_call.assert_awaited_once_with(ctx, "GET", "/templates/tmpl-1")

    @pytest.mark.asyncio
    async def test_create_template(self, registry, tool_context):
        """create_template calls POST /templates with payload."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "tmpl-new", "name": "New"},
        ) as mock_call:
            result = await dispatch(
                "create_template",
                {"name": "New", "config": {"key": "val"}},
                ctx,
                registry,
            )
            assert result["id"] == "tmpl-new"
            mock_call.assert_awaited_once_with(
                ctx, "POST", "/templates", json_data={"name": "New", "config": {"key": "val"}}
            )

    @pytest.mark.asyncio
    async def test_update_template(self, registry, tool_context):
        """update_template calls PUT /templates/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "tmpl-1", "name": "Updated"},
        ) as mock_call:
            result = await dispatch(
                "update_template",
                {"id": "tmpl-1", "name": "Updated"},
                ctx,
                registry,
            )
            assert result["name"] == "Updated"
            mock_call.assert_awaited_once_with(
                ctx, "PUT", "/templates/tmpl-1", json_data={"name": "Updated"}
            )

    @pytest.mark.asyncio
    async def test_delete_template(self, registry, tool_context):
        """delete_template calls DELETE /templates/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"status": "deleted"},
        ) as mock_call:
            result = await dispatch("delete_template", {"id": "tmpl-1"}, ctx, registry)
            assert result["status"] == "deleted"
            mock_call.assert_awaited_once_with(ctx, "DELETE", "/templates/tmpl-1")


class TestStyleTools:
    """Happy-path tests for style tools via mocked call_user_api."""

    @pytest.mark.asyncio
    async def test_list_styles(self, registry, tool_context):
        """list_styles calls GET /styles with optional category param."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"styles": [{"id": "s1", "name": "Cinematic"}]},
        ) as mock_call:
            result = await dispatch("list_styles", {"category": "cinematic"}, ctx, registry)
            assert len(result["styles"]) == 1
            mock_call.assert_awaited_once_with(
                ctx, "GET", "/styles", params={"category": "cinematic"}
            )

    @pytest.mark.asyncio
    async def test_get_style(self, registry, tool_context):
        """get_style calls GET /styles/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "s1", "name": "Cinematic"},
        ) as mock_call:
            result = await dispatch("get_style", {"id": "s1"}, ctx, registry)
            assert result["name"] == "Cinematic"
            mock_call.assert_awaited_once_with(ctx, "GET", "/styles/s1")

    @pytest.mark.asyncio
    async def test_create_style(self, registry, tool_context):
        """create_style calls POST /styles."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "s-new", "name": "Neon"},
        ) as mock_call:
            result = await dispatch(
                "create_style", {"name": "Neon", "params": {"brightness": 10}}, ctx, registry
            )
            assert result["name"] == "Neon"
            mock_call.assert_awaited_once_with(
                ctx, "POST", "/styles", json_data={"name": "Neon", "params": {"brightness": 10}}
            )

    @pytest.mark.asyncio
    async def test_update_style(self, registry, tool_context):
        """update_style calls PUT /styles/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "s1", "name": "Neon V2"},
        ) as mock_call:
            result = await dispatch(
                "update_style", {"id": "s1", "name": "Neon V2"}, ctx, registry
            )
            assert result["name"] == "Neon V2"
            mock_call.assert_awaited_once_with(
                ctx, "PUT", "/styles/s1", json_data={"name": "Neon V2"}
            )

    @pytest.mark.asyncio
    async def test_delete_style(self, registry, tool_context):
        """delete_style calls DELETE /styles/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"status": "deleted"},
        ) as mock_call:
            result = await dispatch("delete_style", {"id": "s1"}, ctx, registry)
            assert result["status"] == "deleted"
            mock_call.assert_awaited_once_with(ctx, "DELETE", "/styles/s1")


class TestAvatarTools:
    """Happy-path tests for avatar tools via mocked call_user_api."""

    @pytest.mark.asyncio
    async def test_list_avatars(self, registry, tool_context):
        """list_avatars calls GET /avatars."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"avatars": [{"id": "a1", "name": "Alice"}], "total": 1},
        ) as mock_call:
            result = await dispatch("list_avatars", {"limit": 10}, ctx, registry)
            assert result["total"] == 1
            mock_call.assert_awaited_once_with(
                ctx, "GET", "/avatars", params={"limit": 10}
            )

    @pytest.mark.asyncio
    async def test_get_avatar(self, registry, tool_context):
        """get_avatar calls GET /avatars/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "a1", "name": "Alice"},
        ) as mock_call:
            result = await dispatch("get_avatar", {"id": "a1"}, ctx, registry)
            assert result["name"] == "Alice"
            mock_call.assert_awaited_once_with(ctx, "GET", "/avatars/a1")

    @pytest.mark.asyncio
    async def test_create_avatar(self, registry, tool_context):
        """create_avatar calls POST /avatars."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "a-new", "name": "Bob"},
        ) as mock_call:
            result = await dispatch(
                "create_avatar",
                {"name": "Bob", "gender": "Male"},
                ctx,
                registry,
            )
            assert result["name"] == "Bob"
            mock_call.assert_awaited_once_with(
                ctx, "POST", "/avatars", json_data={"name": "Bob", "gender": "Male"}
            )

    @pytest.mark.asyncio
    async def test_update_avatar(self, registry, tool_context):
        """update_avatar calls PUT /avatars/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"id": "a1", "name": "Bob V2"},
        ) as mock_call:
            result = await dispatch(
                "update_avatar", {"id": "a1", "name": "Bob V2"}, ctx, registry
            )
            assert result["name"] == "Bob V2"
            mock_call.assert_awaited_once_with(
                ctx, "PUT", "/avatars/a1", json_data={"name": "Bob V2"}
            )

    @pytest.mark.asyncio
    async def test_delete_avatar(self, registry, tool_context):
        """delete_avatar calls DELETE /avatars/{id}."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"status": "deleted"},
        ) as mock_call:
            result = await dispatch("delete_avatar", {"id": "a1"}, ctx, registry)
            assert result["status"] == "deleted"
            mock_call.assert_awaited_once_with(ctx, "DELETE", "/avatars/a1")


class TestAudioTools:
    """Happy-path tests for audio tools via mocked call_user_api."""

    @pytest.mark.asyncio
    async def test_get_audio_status(self, registry, tool_context):
        """get_audio_status calls GET /audio/status."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"available": True, "url": "http://audiocraft:5000"},
        ) as mock_call:
            result = await dispatch("get_audio_status", {}, ctx, registry)
            assert result["available"] is True
            mock_call.assert_awaited_once_with(ctx, "GET", "/audio/status")

    @pytest.mark.asyncio
    async def test_generate_music(self, registry, tool_context):
        """generate_music calls POST /audio/generate-music."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"path": "music/bgm_abc.mp3", "filename": "bgm_abc.mp3"},
        ) as mock_call:
            result = await dispatch(
                "generate_music",
                {"prompt": "upbeat electronic", "duration": 30},
                ctx,
                registry,
            )
            assert result["filename"] == "bgm_abc.mp3"
            mock_call.assert_awaited_once_with(
                ctx,
                "POST",
                "/audio/generate-music",
                json_data={"prompt": "upbeat electronic", "duration": 30},
            )


class TestUploadTools:
    """Happy-path tests for upload URL tools via mocked call_user_api."""

    @pytest.mark.asyncio
    async def test_upload_image_url(self, registry, tool_context):
        """upload_image_url calls POST /uploads/image-url and returns URL only."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"url": "https://cdn.example.com/img.jpg"},
        ) as mock_call:
            result = await dispatch(
                "upload_image_url", {"url": "https://example.com/img.jpg"}, ctx, registry
            )
            assert result["url"] == "https://cdn.example.com/img.jpg"
            mock_call.assert_awaited_once_with(
                ctx, "POST", "/uploads/image-url", json_data={"url": "https://example.com/img.jpg"}
            )

    @pytest.mark.asyncio
    async def test_upload_video_url(self, registry, tool_context):
        """upload_video_url calls POST /uploads/video-url."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"url": "https://cdn.example.com/vid.mp4"},
        ) as mock_call:
            result = await dispatch(
                "upload_video_url", {"url": "https://example.com/vid.mp4"}, ctx, registry
            )
            assert result["url"] == "https://cdn.example.com/vid.mp4"
            mock_call.assert_awaited_once_with(
                ctx, "POST", "/uploads/video-url", json_data={"url": "https://example.com/vid.mp4"}
            )

    @pytest.mark.asyncio
    async def test_upload_audio_url(self, registry, tool_context):
        """upload_audio_url calls POST /uploads/audio-url."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"url": "https://cdn.example.com/audio.mp3"},
        ) as mock_call:
            result = await dispatch(
                "upload_audio_url", {"url": "https://example.com/audio.mp3"}, ctx, registry
            )
            assert result["url"] == "https://cdn.example.com/audio.mp3"
            mock_call.assert_awaited_once_with(
                ctx, "POST", "/uploads/audio-url", json_data={"url": "https://example.com/audio.mp3"}
            )


class TestUserSettingsTools:
    """Happy-path tests for user settings tools via mocked call_user_api."""

    @pytest.mark.asyncio
    async def test_get_user_settings(self, registry, tool_context):
        """get_user_settings calls GET /users/settings."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"storage_backend": "local", "preferences": {"theme": "dark"}},
        ) as mock_call:
            result = await dispatch("get_user_settings", {}, ctx, registry)
            assert result["storage_backend"] == "local"
            mock_call.assert_awaited_once_with(ctx, "GET", "/users/settings")

    @pytest.mark.asyncio
    async def test_update_user_settings(self, registry, tool_context):
        """update_user_settings calls PUT /users/settings."""
        ctx = tool_context()
        with patch(
            "app.chatbot.api_tools.call_user_api",
            new_callable=AsyncMock,
            return_value={"storage_backend": "s3", "preferences": {"theme": "light"}},
        ) as mock_call:
            result = await dispatch(
                "update_user_settings",
                {"storage_backend": "s3", "preferences": {"theme": "light"}},
                ctx,
                registry,
            )
            assert result["storage_backend"] == "s3"
            mock_call.assert_awaited_once_with(
                ctx,
                "PUT",
                "/users/settings",
                json_data={"storage_backend": "s3", "preferences": {"theme": "light"}},
            )


class TestBlockedPaths:
    """Negative tests: admin paths should be blocked."""

    @pytest.mark.asyncio
    async def test_admin_path_blocked(self, registry, tool_context):
        """Direct call to an admin path via call_user_api returns blocked error."""
        from app.chatbot.api_tools import call_user_api

        ctx = tool_context()
        result = await call_user_api(ctx, "GET", "/api/admin/users")
        assert result["error"] == "forbidden"
        assert "Admin" in result["message"]

    @pytest.mark.asyncio
    async def test_provider_write_blocked(self, registry, tool_context):
        """Provider write operations are blocked."""
        from app.chatbot.api_tools import call_user_api

        ctx = tool_context()
        result = await call_user_api(ctx, "POST", "/api/providers", json_data={"name": "test"})
        assert result["error"] == "forbidden"
