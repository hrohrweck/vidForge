from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import ModelConfig, Provider


def _provider_payload(name="Test Provider", provider_type="comfyui_direct"):
    return {
        "name": name,
        "provider_type": provider_type,
        "config": {"comfyui_url": "http://localhost:8188"},
        "daily_budget_limit": 10.0,
        "priority": 1,
    }


def _model_payload(overrides=None):
    base = {
        "model_id": "flux-schnell",
        "provider_model_id": "flux-schnell-v1",
        "display_name": "Flux Schnell",
        "modality": "image",
    }
    if overrides:
        base.update(overrides)
    return base


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Provider CRUD ──────────────────────────────────────────────────


class TestProviderCRUD:
    @pytest.mark.asyncio
    async def test_create_provider_with_valid_type(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        resp = await client.post(
            "/api/providers",
            json=_provider_payload(provider_type="comfyui_direct"),
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["provider_type"] == "comfyui_direct"
        assert data["name"] == "Test Provider"
        assert data["redirect_url"] == f"/admin/models?provider={data['id']}"

    @pytest.mark.asyncio
    async def test_create_provider_with_invalid_type_returns_400(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.post(
            "/api/providers",
            json=_provider_payload(provider_type="nonexistent_provider"),
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 400
        assert "Unknown provider type" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_duplicate_name_rejected(
        self, client: AsyncClient, superuser_token: str
    ):
        payload = _provider_payload(name="UniqueProvider")
        r1 = await client.post(
            "/api/providers", json=payload, headers=_auth_headers(superuser_token)
        )
        assert r1.status_code == 200
        r2 = await client.post(
            "/api/providers", json=payload, headers=_auth_headers(superuser_token)
        )
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_list_providers(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="ListTest",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.get(
            "/api/providers", headers=_auth_headers(superuser_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(d["name"] == "ListTest" for d in data)

    @pytest.mark.asyncio
    async def test_get_provider_by_id(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="GetTest",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.get(
            f"/api/providers/{p.id}", headers=_auth_headers(superuser_token)
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetTest"

    @pytest.mark.asyncio
    async def test_get_provider_not_found(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.get(
            f"/api/providers/{uuid4()}", headers=_auth_headers(superuser_token)
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_provider(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="UpdateTest",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.patch(
            f"/api/providers/{p.id}",
            json={"name": "UpdatedName"},
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "UpdatedName"

    @pytest.mark.asyncio
    async def test_delete_provider(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="DeleteTest",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.delete(
            f"/api/providers/{p.id}", headers=_auth_headers(superuser_token)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


# ── Provider Auth ──────────────────────────────────────────────────


class TestProviderAuth:
    @pytest.mark.asyncio
    async def test_regular_user_cannot_create_provider(
        self, client: AsyncClient, regular_user_token: str
    ):
        resp = await client.post(
            "/api/providers",
            json=_provider_payload(),
            headers=_auth_headers(regular_user_token),
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_regular_user_cannot_delete_provider(
        self, client: AsyncClient, regular_user_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="AuthDeleteTest",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.delete(
            f"/api/providers/{p.id}", headers=_auth_headers(regular_user_token)
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(
        self, client: AsyncClient
    ):
        resp = await client.get("/api/providers")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_regular_user_can_list_providers(
        self, client: AsyncClient, regular_user_token: str
    ):
        resp = await client.get(
            "/api/providers", headers=_auth_headers(regular_user_token)
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_regular_user_can_get_provider(
        self, client: AsyncClient, regular_user_token: str, db_session
    ):
        p = Provider(
            id=uuid4(),
            name="ViewableProvider",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(p)
        await db_session.commit()

        resp = await client.get(
            f"/api/providers/{p.id}", headers=_auth_headers(regular_user_token)
        )
        assert resp.status_code == 200


# ── Generic Model CRUD ────────────────────────────────────────────


class TestModelCRUD:
    @pytest.fixture(autouse=True)
    async def _setup(self, db_session):
        self.provider = Provider(
            id=uuid4(),
            name="ModelTestProvider",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(self.provider)
        await db_session.commit()
        self.pid = str(self.provider.id)

    @pytest.mark.asyncio
    async def test_list_models_empty(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.get(
            f"/api/providers/{self.pid}/models",
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_model(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.post(
            f"/api/providers/{self.pid}/models",
            json=_model_payload(),
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model_id"] == "flux-schnell"
        assert data["modality"] == "image"
        assert data["provider_id"] == self.pid

    @pytest.mark.asyncio
    async def test_create_model_missing_modality(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.post(
            f"/api/providers/{self.pid}/models",
            json={"model_id": "x", "provider_model_id": "x", "display_name": "X"},
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_model_provider_not_found(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.post(
            f"/api/providers/{uuid4()}/models",
            json=_model_payload(),
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_models_with_data(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        mc = ModelConfig(
            id=uuid4(),
            provider_id=self.provider.id,
            model_id="flux-schnell",
            provider_model_id="flux-schnell-v1",
            display_name="Flux Schnell",
            modality="image",
            endpoint_type="comfyui",
        )
        db_session.add(mc)
        await db_session.commit()

        resp = await client.get(
            f"/api/providers/{self.pid}/models",
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(m["model_id"] == "flux-schnell" for m in data)

    @pytest.mark.asyncio
    async def test_update_model(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        mc = ModelConfig(
            id=uuid4(),
            provider_id=self.provider.id,
            model_id="old-model",
            provider_model_id="old-model-v1",
            display_name="Old Model",
            modality="image",
            endpoint_type="comfyui",
        )
        db_session.add(mc)
        await db_session.commit()

        resp = await client.patch(
            f"/api/providers/{self.pid}/models/{mc.id}",
            json={"display_name": "Renamed Model"},
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["display_name"] == "Renamed Model"

    @pytest.mark.asyncio
    async def test_update_model_not_found(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.patch(
            f"/api/providers/{self.pid}/models/{uuid4()}",
            json={"display_name": "Ghost"},
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_model_soft_deletes(
        self, client: AsyncClient, superuser_token: str, db_session
    ):
        mc = ModelConfig(
            id=uuid4(),
            provider_id=self.provider.id,
            model_id="to-delete",
            provider_model_id="to-delete-v1",
            display_name="To Delete",
            modality="image",
            endpoint_type="comfyui",
            is_active=True,
        )
        db_session.add(mc)
        await db_session.commit()

        resp = await client.delete(
            f"/api/providers/{self.pid}/models/{mc.id}",
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp_list = await client.get(
            f"/api/providers/{self.pid}/models",
            headers=_auth_headers(superuser_token),
        )
        found = next(
            (m for m in resp_list.json() if m["id"] == str(mc.id)), None
        )
        assert found is not None
        assert found["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_model_not_found(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.delete(
            f"/api/providers/{self.pid}/models/{uuid4()}",
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_regular_user_cannot_create_model(
        self, client: AsyncClient, regular_user_token: str
    ):
        resp = await client.post(
            f"/api/providers/{self.pid}/models",
            json=_model_payload(),
            headers=_auth_headers(regular_user_token),
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_regular_user_can_list_models(
        self, client: AsyncClient, regular_user_token: str
    ):
        resp = await client.get(
            f"/api/providers/{self.pid}/models",
            headers=_auth_headers(regular_user_token),
        )
        assert resp.status_code == 200


# ── Model Sync ────────────────────────────────────────────────────


class TestModelSync:
    @pytest.fixture(autouse=True)
    async def _setup(self, db_session):
        self.provider = Provider(
            id=uuid4(),
            name="SyncTestProvider",
            provider_type="comfyui_direct",
            config={"comfyui_url": "http://localhost:8188"},
        )
        db_session.add(self.provider)
        await db_session.commit()
        self.pid = str(self.provider.id)

    @pytest.mark.asyncio
    async def test_sync_models_success(
        self, client: AsyncClient, superuser_token: str, mocker
    ):
        mock_instance = mocker.magic_mock()
        mock_instance.sync_models = AsyncMock(
            return_value=[
                {
                    "model_id": "synced-model-1",
                    "provider_model_id": "synced-1",
                    "display_name": "Synced Model 1",
                    "modality": "image",
                    "endpoint_type": "comfyui",
                },
            ]
        )
        mock_instance.shutdown = AsyncMock()

        with mocker.patch(
            "app.api.providers.registry.create",
            return_value=mock_instance,
        ):
            resp = await client.post(
                f"/api/providers/{self.pid}/sync-models",
                headers=_auth_headers(superuser_token),
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["synced_count"] == 1
        assert len(data["models"]) == 1
        assert data["models"][0]["model_id"] == "synced-model-1"

    @pytest.mark.asyncio
    async def test_sync_models_unsupported_provider(
        self, client: AsyncClient, superuser_token: str, mocker
    ):
        mock_instance = mocker.magic_mock()
        mock_instance.sync_models = AsyncMock(
            side_effect=NotImplementedError("Provider does not support model sync")
        )
        mock_instance.shutdown = AsyncMock()

        with mocker.patch(
            "app.api.providers.registry.create",
            return_value=mock_instance,
        ):
            resp = await client.post(
                f"/api/providers/{self.pid}/sync-models",
                headers=_auth_headers(superuser_token),
            )

        assert resp.status_code == 400
        assert "does not support model sync" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_sync_models_provider_not_found(
        self, client: AsyncClient, superuser_token: str
    ):
        resp = await client.post(
            f"/api/providers/{uuid4()}/sync-models",
            headers=_auth_headers(superuser_token),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_sync_models_regular_user_forbidden(
        self, client: AsyncClient, regular_user_token: str
    ):
        resp = await client.post(
            f"/api/providers/{self.pid}/sync-models",
            headers=_auth_headers(regular_user_token),
        )
        assert resp.status_code in (401, 403)
