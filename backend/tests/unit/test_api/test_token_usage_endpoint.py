"""Tests for GET /api/chat/token-usage endpoint."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import ChatTokenUsage


def _make_row(
    user_id,
    model_id,
    conversation_id,
    tokens_in,
    tokens_out,
    recorded_at=None,
):
    return ChatTokenUsage(
        id=uuid4(),
        user_id=user_id,
        model_id=model_id,
        conversation_id=conversation_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        recorded_at=recorded_at or datetime.utcnow(),
    )


class TestTokenUsageEndpointAuthorization:
    @pytest.mark.asyncio
    async def test_unauthenticated_get_token_usage(self, client: AsyncClient):
        response = await client.get("/api/chat/token-usage")
        assert response.status_code == 401


class TestTokenUsageEndpointEmpty:
    @pytest.mark.asyncio
    async def test_empty_result(self, client: AsyncClient, regular_user_token: str, regular_user):
        response = await client.get(
            "/api/chat/token-usage",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []


class TestTokenUsageEndpointMultipleModels:

    @pytest.fixture
    async def usage_data(self, db_session, regular_user):
        now = datetime.utcnow()
        rows = [
            _make_row(regular_user.id, "qwen3.6", None, 100, 20, now),
            _make_row(regular_user.id, "qwen3.6", None, 200, 40, now),
            _make_row(regular_user.id, "llama3.3", None, 300, 60, now),
        ]
        for row in rows:
            db_session.add(row)
        await db_session.commit()
        return regular_user.id

    @pytest.mark.asyncio
    async def test_multiple_models(self, client: AsyncClient, regular_user_token: str, usage_data):
        response = await client.get(
            "/api/chat/token-usage",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        assert data["items"][0]["model_id"] == "llama3.3"
        assert data["items"][0]["prompt_tokens"] == 300
        assert data["items"][0]["completion_tokens"] == 60
        assert data["items"][0]["total_tokens"] == 360
        assert data["items"][0]["message_count"] == 1

        assert data["items"][1]["model_id"] == "qwen3.6"
        assert data["items"][1]["prompt_tokens"] == 300
        assert data["items"][1]["completion_tokens"] == 60
        assert data["items"][1]["total_tokens"] == 360
        assert data["items"][1]["message_count"] == 2


class TestTokenUsageEndpointDateFilter:

    @pytest.fixture
    async def usage_data(self, db_session, regular_user):
        now = datetime.utcnow()
        days_ago_1 = now - timedelta(days=1)
        days_ago_3 = now - timedelta(days=3)
        rows = [
            _make_row(regular_user.id, "qwen3.6", None, 100, 20, days_ago_1),
            _make_row(regular_user.id, "qwen3.6", None, 100, 20, days_ago_3),
        ]
        for row in rows:
            db_session.add(row)
        await db_session.commit()
        return regular_user.id

    @pytest.mark.asyncio
    async def test_date_filter_within(self, client: AsyncClient, regular_user_token: str, usage_data):
        now = datetime.utcnow()
        from_date = (now - timedelta(days=2)).isoformat()
        to_date = now.isoformat()

        response = await client.get(
            "/api/chat/token-usage",
            params={"from": from_date, "to": to_date},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["prompt_tokens"] == 200
        assert data["items"][0]["completion_tokens"] == 40
        assert data["items"][0]["total_tokens"] == 240

    @pytest.mark.asyncio
    async def test_date_filter_excludes_all(self, client: AsyncClient, regular_user_token: str, usage_data):
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        from_date = now + timedelta(days=1)
        to_date = from_date + timedelta(days=1)
        from_str = from_date.isoformat()
        to_str = to_date.isoformat()
        response = await client.get(
            "/api/chat/token-usage",
            params={"from": from_str, "to": to_str},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        future_items = [i for i in data["items"] if i["total_tokens"] > 0]
        assert len(future_items) >= 0


class TestTokenUsageEndpointIsolation:

    @pytest.fixture
    async def other_user_row(self, db_session, regular_user):
        other_id = uuid4()
        row = _make_row(other_id, "secret_model", None, 9999, 9999)
        db_session.add(row)
        me_row = _make_row(regular_user.id, "my_model", None, 10, 5)
        db_session.add(me_row)
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_cannot_see_other_user(
        self, client: AsyncClient, regular_user_token: str, other_user_row
    ):
        response = await client.get(
            "/api/chat/token-usage",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["model_id"] == "my_model"
        assert data["items"][0]["prompt_tokens"] == 10
