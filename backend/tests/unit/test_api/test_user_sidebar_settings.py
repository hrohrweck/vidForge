import pytest
from httpx import AsyncClient

from app.database import UserSettings


class TestSidebarSettingsAPI:
    @pytest.mark.asyncio
    async def test_unauthenticated_get_returns_401(self, client: AsyncClient):
        response = await client.get("/api/users/settings/sidebar")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_put_returns_401(self, client: AsyncClient):
        response = await client.put("/api/users/settings/sidebar", json={"sidebar_open": False})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_get_no_settings_returns_default_true(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/users/settings/sidebar",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data == {"sidebar_open": True}

    @pytest.mark.asyncio
    async def test_put_false_creates_settings_and_get_returns_false(
        self, client: AsyncClient, regular_user_token: str, db_session
    ):
        put_response = await client.put(
            "/api/users/settings/sidebar",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"sidebar_open": False},
        )
        assert put_response.status_code == 200
        assert put_response.json() == {"sidebar_open": False}

        get_response = await client.get(
            "/api/users/settings/sidebar",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert get_response.status_code == 200
        assert get_response.json() == {"sidebar_open": False}

    @pytest.mark.asyncio
    async def test_put_preserves_default_chat_model(
        self, client: AsyncClient, regular_user, regular_user_token: str, db_session
    ):
        settings = UserSettings(
            user_id=regular_user.id,
            preferences={"default_chat_model": "gpt-4"},
        )
        db_session.add(settings)
        await db_session.commit()

        put_response = await client.put(
            "/api/users/settings/sidebar",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"sidebar_open": False},
        )
        assert put_response.status_code == 200

        await db_session.refresh(settings)
        assert settings.preferences["default_chat_model"] == "gpt-4"
        assert settings.preferences["ui"]["sidebar_open"] is False

    @pytest.mark.asyncio
    async def test_put_preserves_unrelated_ui_keys(
        self, client: AsyncClient, regular_user, regular_user_token: str, db_session
    ):
        settings = UserSettings(
            user_id=regular_user.id,
            preferences={
                "default_chat_model": "gpt-4",
                "ui": {"theme": "dark", "sidebar_open": True},
            },
        )
        db_session.add(settings)
        await db_session.commit()

        put_response = await client.put(
            "/api/users/settings/sidebar",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"sidebar_open": False},
        )
        assert put_response.status_code == 200

        await db_session.refresh(settings)
        assert settings.preferences["ui"]["theme"] == "dark"
        assert settings.preferences["ui"]["sidebar_open"] is False
        assert settings.preferences["default_chat_model"] == "gpt-4"
