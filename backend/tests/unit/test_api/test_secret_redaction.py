from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import Provider


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestProviderSecretRedaction:
    @pytest.mark.asyncio
    async def test_list_providers_hides_api_key_for_non_admin(
        self, client: AsyncClient, regular_user_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="SecretProvider",
            provider_type="poe",
            config={"api_key": "super-secret", "base_url": "https://api.poe.com"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.get("/api/providers", headers=_auth_headers(regular_user_token))
        assert resp.status_code == 200
        data = resp.json()
        provider = next(d for d in data if d["name"] == "SecretProvider")
        assert provider["config"]["api_key"] == "***"
        assert provider["config"]["base_url"] == "https://api.poe.com"

    @pytest.mark.asyncio
    async def test_get_provider_hides_api_key_for_non_admin(
        self, client: AsyncClient, regular_user_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="SecretProvider2",
            provider_type="runpod",
            config={"api_key": "runpod-secret", "region": "us-east"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.get(
            f"/api/providers/{p.id}", headers=_auth_headers(regular_user_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["config"]["api_key"] == "***"
        assert data["config"]["region"] == "us-east"

    @pytest.mark.asyncio
    async def test_update_provider_skips_mask_sentinel(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="MaskProvider",
            provider_type="poe",
            config={"api_key": "real-secret", "base_url": "https://api.poe.com"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.patch(
            f"/api/providers/{p.id}",
            json={"config": {"api_key": "***", "base_url": "https://new.poe.com"}},
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200

        # Fetch raw from DB to confirm real key is preserved
        await db_session.refresh(p)
        assert p.config["api_key"] == "real-secret"
        assert p.config["base_url"] == "https://new.poe.com"


class TestStorageConfigRedaction:
    @pytest.mark.asyncio
    async def test_storage_config_for_non_admin_is_minimal(
        self, client: AsyncClient, regular_user_token: str
    ):
        resp = await client.get("/api/storage/config", headers=_auth_headers(regular_user_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"backend": "local"}

    @pytest.mark.asyncio
    async def test_storage_config_for_admin_includes_full_config(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.get("/api/storage/config", headers=_auth_headers(superuser_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["backend"] == "local"
        assert "config" in data
