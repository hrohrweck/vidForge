from __future__ import annotations

import pytest
from uuid import uuid4

from app.database import Provider
from app.main import app
from app.services.providers import registry


@pytest.fixture
async def sync_provider(db_session):
    provider = Provider(
        id=uuid4(),
        name="Test Sync",
        provider_type="ollama",
        config={"base_url": "http://localhost"},
        is_active=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


class FakeProvider:
    async def sync_models(self):
        return [
            {
                "model_id": "llama3",
                "provider_model_id": "llama3",
                "display_name": "Llama 3",
                "modality": "text",
                "endpoint_type": "chat_completions",
                "capabilities": {"accepts_text": True, "outputs_text": True},
            }
        ]

    async def shutdown(self):
        pass


@pytest.mark.asyncio
async def test_sync_models_upserts_models(client, sync_provider, superuser_token, monkeypatch):
    async def fake_create(*args, **kwargs):
        return FakeProvider()

    monkeypatch.setattr(registry, "create", fake_create)

    response = await client.post(
        f"/api/providers/{sync_provider.id}/sync-models",
        headers={"Authorization": f"Bearer {superuser_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["synced_count"] == 1
    assert len(data["models"]) == 1
    assert data["models"][0]["model_id"] == "llama3"


@pytest.mark.asyncio
async def test_sync_models_preserves_manual_cost_config(client, sync_provider, superuser_token, monkeypatch, db_session):
    from app.services.model_config_service import ModelConfigService

    config = await ModelConfigService.create(
        db_session,
        {
            "provider_id": sync_provider.id,
            "model_id": "llama3",
            "provider_model_id": "llama3",
            "display_name": "Llama 3",
            "modality": "text",
            "endpoint_type": "chat_completions",
            "cost_config": {"cost_per_1k_prompt_tokens": 0.01, "currency": "USD"},
        },
    )
    await db_session.commit()

    async def fake_create(*args, **kwargs):
        return FakeProvider()

    monkeypatch.setattr(registry, "create", fake_create)

    response = await client.post(
        f"/api/providers/{sync_provider.id}/sync-models",
        headers={"Authorization": f"Bearer {superuser_token}"},
    )
    assert response.status_code == 200

    refreshed = await ModelConfigService.get_by_id(db_session, "llama3", sync_provider.id)
    assert refreshed is not None
    assert refreshed.cost_config["cost_per_1k_prompt_tokens"] == 0.01
