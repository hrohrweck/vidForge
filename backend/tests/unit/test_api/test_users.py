import pytest
from httpx import AsyncClient

from app.database import UserSettings


class TestChatAutonomySettingsAPI:
    @pytest.mark.asyncio
    async def test_unauthenticated_get_returns_401(self, client: AsyncClient):
        response = await client.get("/api/users/settings/chat-autonomy")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_put_returns_401(self, client: AsyncClient):
        response = await client.put(
            "/api/users/settings/chat-autonomy", json={"chat_autonomy": "autonomous"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_get_no_settings_returns_null(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/users/settings/chat-autonomy",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data == {"chat_autonomy": None}

    @pytest.mark.asyncio
    async def test_put_autonomous_creates_settings_and_get_returns_value(
        self, client: AsyncClient, regular_user_token: str, db_session
    ):
        put_response = await client.put(
            "/api/users/settings/chat-autonomy",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"chat_autonomy": "autonomous"},
        )
        assert put_response.status_code == 200
        assert put_response.json() == {"chat_autonomy": "autonomous"}

        get_response = await client.get(
            "/api/users/settings/chat-autonomy",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert get_response.status_code == 200
        assert get_response.json() == {"chat_autonomy": "autonomous"}

    @pytest.mark.asyncio
    async def test_put_confirm_creates_settings_and_get_returns_value(
        self, client: AsyncClient, regular_user_token: str, db_session
    ):
        put_response = await client.put(
            "/api/users/settings/chat-autonomy",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"chat_autonomy": "confirm"},
        )
        assert put_response.status_code == 200
        assert put_response.json() == {"chat_autonomy": "confirm"}

        get_response = await client.get(
            "/api/users/settings/chat-autonomy",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert get_response.status_code == 200
        assert get_response.json() == {"chat_autonomy": "confirm"}

    @pytest.mark.asyncio
    async def test_put_invalid_value_returns_422(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.put(
            "/api/users/settings/chat-autonomy",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"chat_autonomy": "invalid"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_put_preserves_other_preferences(
        self, client: AsyncClient, regular_user, regular_user_token: str, db_session
    ):
        settings = UserSettings(
            user_id=regular_user.id,
            preferences={"default_chat_model": "gpt-4", "ui": {"sidebar_open": False}},
        )
        db_session.add(settings)
        await db_session.commit()

        put_response = await client.put(
            "/api/users/settings/chat-autonomy",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"chat_autonomy": "autonomous"},
        )
        assert put_response.status_code == 200

        await db_session.refresh(settings)
        assert settings.preferences["chat_autonomy"] == "autonomous"
        assert settings.preferences["default_chat_model"] == "gpt-4"
        assert settings.preferences["ui"]["sidebar_open"] is False


class TestUserSettingsAPI:
    @pytest.mark.asyncio
    async def test_put_settings_merges_preferences_preserving_chat_autonomy(
        self, client: AsyncClient, regular_user, regular_user_token: str, db_session
    ):
        settings = UserSettings(
            user_id=regular_user.id,
            preferences={"chat_autonomy": "autonomous"},
        )
        db_session.add(settings)
        await db_session.commit()

        put_response = await client.put(
            "/api/users/settings",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"preferences": {"auto_create_jobs": True}},
        )
        assert put_response.status_code == 200

        data = put_response.json()
        assert data["preferences"]["chat_autonomy"] == "autonomous"
        assert data["preferences"]["auto_create_jobs"] is True

        await db_session.refresh(settings)
        assert settings.preferences["chat_autonomy"] == "autonomous"
        assert settings.preferences["auto_create_jobs"] is True
