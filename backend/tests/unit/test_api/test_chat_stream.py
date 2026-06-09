import json
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import Conversation


class TestChatStreamAPI:
    @pytest.fixture
    async def conversation(self, db_session, regular_user):
        conv = Conversation(
            id=uuid4(),
            user_id=regular_user.id,
            title="Test Chat",
            model_id="default",
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)
        return conv

    @pytest.mark.asyncio
    async def test_stream_completes_with_done_event(
        self, client: AsyncClient, regular_user_token: str, conversation
    ):
        async def mock_run_turn(*args, **kwargs):
            yield ("token", {"content": "hello"})
            yield ("done", {})

        with patch("app.api.chat.ChatOrchestrator") as mock_orchestrator:
            instance = mock_orchestrator.return_value
            instance.run_turn = mock_run_turn

            response = await client.post(
                f"/api/chat/conversations/{conversation.id}/messages",
                headers={"Authorization": f"Bearer {regular_user_token}"},
                json={"content": "hi", "model_id": "default"},
            )
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-accel-buffering"] == "no"

            body = response.text
            events = []
            for line in body.strip().split("\n\n"):
                if not line:
                    continue
                event_line, data_line = line.split("\n", 1)
                event_type = event_line.split(": ", 1)[1]
                data = json.loads(data_line.split(": ", 1)[1])
                events.append((event_type, data))

            assert events[0] == ("token", {"content": "hello"})
            assert events[1] == ("done", {})

    @pytest.mark.asyncio
    async def test_stream_other_user_conversation_returns_404(
        self, client: AsyncClient, superuser_token: str, conversation
    ):
        response = await client.post(
            f"/api/chat/conversations/{conversation.id}/messages",
            headers={"Authorization": f"Bearer {superuser_token}"},
            json={"content": "hi", "model_id": "default"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stream_tool_call_events_flow_through(
        self, client: AsyncClient, regular_user_token: str, conversation
    ):
        async def mock_run_turn(*args, **kwargs):
            yield ("tool_call_start", {"id": "tc1", "name": "get_weather", "arguments": {"city": "Paris"}})
            yield ("tool_call_result", {"id": "tc1", "name": "get_weather", "kind": "tool_result", "result": {"temp": 22}})
            yield ("done", {})

        with patch("app.api.chat.ChatOrchestrator") as mock_orchestrator:
            instance = mock_orchestrator.return_value
            instance.run_turn = mock_run_turn

            response = await client.post(
                f"/api/chat/conversations/{conversation.id}/messages",
                headers={"Authorization": f"Bearer {regular_user_token}"},
                json={"content": "what's the weather?", "model_id": "default"},
            )
            assert response.status_code == 200

            body = response.text
            events = []
            for line in body.strip().split("\n\n"):
                if not line:
                    continue
                event_line, data_line = line.split("\n", 1)
                event_type = event_line.split(": ", 1)[1]
                data = json.loads(data_line.split(": ", 1)[1])
                events.append((event_type, data))

            assert events[0] == (
                "tool_call_start",
                {"id": "tc1", "name": "get_weather", "arguments": {"city": "Paris"}},
            )
            assert events[1] == (
                "tool_call_result",
                {"id": "tc1", "name": "get_weather", "kind": "tool_result", "result": {"temp": 22}},
            )
            assert events[2] == ("done", {})

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_stream_messages(self, client: AsyncClient):
        response = await client.post(
            f"/api/chat/conversations/{uuid4()}/messages",
            json={"content": "hi", "model_id": "default"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_stream_preserves_whitespace_in_tokens(
        self, client: AsyncClient, regular_user_token: str, conversation
    ):
        """Ensure spaces in individual tokens are not stripped during streaming.

        Regression: _strip_thinking() called .strip() on each token, removing
        spaces between words (e.g. "hello" + " world" became "helloworld").
        """
        async def mock_run_turn(*args, **kwargs):
            # Simulate tokens that include spaces (as LLM streaming often delivers)
            yield ("token", {"content": "I'd be "})
            yield ("token", {"content": "happy to help"})
            yield ("done", {})

        with patch("app.api.chat.ChatOrchestrator") as mock_orchestrator:
            instance = mock_orchestrator.return_value
            instance.run_turn = mock_run_turn

            response = await client.post(
                f"/api/chat/conversations/{conversation.id}/messages",
                headers={"Authorization": f"Bearer {regular_user_token}"},
                json={"content": "hi", "model_id": "default"},
            )
            assert response.status_code == 200

            body = response.text
            events = []
            for line in body.strip().split("\n\n"):
                if not line:
                    continue
                event_line, data_line = line.split("\n", 1)
                event_type = event_line.split(": ", 1)[1]
                data = json.loads(data_line.split(": ", 1)[1])
                events.append((event_type, data))

            assert events[0] == ("token", {"content": "I'd be "})
            assert events[1] == ("token", {"content": "happy to help"})
            assert events[2] == ("done", {})
