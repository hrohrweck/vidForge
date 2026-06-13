"""Tests for chat autonomy and job-draft presentation tools."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.chatbot.tools import (
    ToolContext,
    _handle_get_chat_autonomy,
    _handle_present_job_draft,
    _handle_set_chat_autonomy,
    create_builtin_registry,
)


@pytest.fixture
def ctx():
    return ToolContext(user_id=str(uuid4()))


@pytest.fixture
def ctx_with_conversation(ctx):
    return ToolContext(
        user_id=ctx.user_id,
        conversation_id=str(uuid4()),
        db=AsyncMock(),
    )


class TestToolRegistration:
    def test_autonomy_tools_registered(self):
        registry = create_builtin_registry()
        names = set(registry.list_all().keys())
        assert {"present_job_draft", "set_chat_autonomy", "get_chat_autonomy"}.issubset(names)


class TestPresentJobDraft:
    @pytest.mark.asyncio
    async def test_happy_path_builds_draft(self, ctx):
        result = await _handle_present_job_draft(
            ctx,
            {
                "template": "prompt_to_video",
                "prompt": "a cinematic dragon",
                "duration": 45,
                "style": "fantasy",
                "aspect_ratio": "9:16",
                "avatars": ["avatar-1", {"avatar_id": "avatar-2"}],
                "image_model": "flux-schnell",
                "video_model": "wan-2.2",
            },
        )

        assert result == {
            "kind": "job_draft",
            "action": "draft",
            "draft": {
                "template": "prompt_to_video",
                "prompt": "a cinematic dragon",
                "duration": 45,
                "style": "fantasy",
                "aspect_ratio": "9:16",
                "avatars": [{"avatar_id": "avatar-1"}, {"avatar_id": "avatar-2"}],
                "image_model": "flux-schnell",
                "video_model": "wan-2.2",
            },
        }

    @pytest.mark.asyncio
    async def test_applies_defaults(self, ctx):
        result = await _handle_present_job_draft(
            ctx, {"template": "prompt_to_video", "prompt": "a cinematic dragon"}
        )

        draft = result["draft"]
        assert draft["duration"] == 30
        assert draft["style"] == "realistic"
        assert draft["aspect_ratio"] == "16:9"
        assert "image_model" not in draft
        assert "video_model" not in draft
        assert "avatars" not in draft

    @pytest.mark.asyncio
    async def test_missing_template(self, ctx):
        result = await _handle_present_job_draft(ctx, {"prompt": "hello"})
        assert result["error"] == "missing_argument"
        assert "template" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_prompt(self, ctx):
        result = await _handle_present_job_draft(ctx, {"template": "prompt_to_video"})
        assert result["error"] == "missing_argument"
        assert "prompt" in result["message"]

    @pytest.mark.asyncio
    async def test_resolves_template_name_to_uuid(self, ctx_with_conversation):
        from unittest.mock import MagicMock

        template_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = template_id
        ctx_with_conversation.db.execute.return_value = mock_result
        ctx_with_conversation.db.add = MagicMock(return_value=None)

        with patch(
            "app.api.websocket.manager.broadcast_chat_message",
            new_callable=AsyncMock,
        ):
            result = await _handle_present_job_draft(
                ctx_with_conversation,
                {"template": "Prompt to Video", "prompt": "a cinematic dragon"},
            )

        ctx_with_conversation.db.execute.assert_awaited_once()
        assert result["draft"]["template"] == str(template_id)


class TestSetChatAutonomy:
    @pytest.mark.asyncio
    async def test_sets_autonomous_mode(self, ctx_with_conversation):
        with patch(
            "app.chatbot.tools.ChatAutonomyService.set_mode", new_callable=AsyncMock
        ) as mock:
            result = await _handle_set_chat_autonomy(
                ctx_with_conversation, {"mode": "autonomous"}
            )

        assert result == {"mode": "autonomous"}
        mock.assert_awaited_once()
        args = mock.await_args.args
        assert args[0] is ctx_with_conversation.db
        assert args[1] == UUID(ctx_with_conversation.conversation_id)
        assert args[2] == UUID(ctx_with_conversation.user_id)
        assert args[3] == "autonomous"

    @pytest.mark.asyncio
    async def test_sets_confirm_mode(self, ctx_with_conversation):
        with patch(
            "app.chatbot.tools.ChatAutonomyService.set_mode", new_callable=AsyncMock
        ) as mock:
            result = await _handle_set_chat_autonomy(
                ctx_with_conversation, {"mode": "confirm"}
            )

        assert result == {"mode": "confirm"}
        mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_error(self, ctx_with_conversation):
        with patch(
            "app.chatbot.tools.ChatAutonomyService.set_mode", new_callable=AsyncMock
        ) as mock:
            result = await _handle_set_chat_autonomy(
                ctx_with_conversation, {"mode": "freeforall"}
            )

        assert result["error"] == "invalid_mode"
        mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_context_returns_error(self, ctx):
        result = await _handle_set_chat_autonomy(ctx, {"mode": "autonomous"})
        assert result["error"] == "missing_context"


class TestGetChatAutonomy:
    @pytest.mark.asyncio
    async def test_gets_current_mode(self, ctx_with_conversation):
        with patch(
            "app.chatbot.tools.ChatAutonomyService.get_mode",
            new_callable=AsyncMock,
            return_value="autonomous",
        ) as mock:
            result = await _handle_get_chat_autonomy(ctx_with_conversation, {})

        assert result == {"mode": "autonomous"}
        mock.assert_awaited_once_with(
            ctx_with_conversation.db,
            UUID(ctx_with_conversation.conversation_id),
            UUID(ctx_with_conversation.user_id),
        )

    @pytest.mark.asyncio
    async def test_missing_context_defaults_to_confirm(self, ctx):
        result = await _handle_get_chat_autonomy(ctx, {})
        assert result == {"mode": "confirm"}
