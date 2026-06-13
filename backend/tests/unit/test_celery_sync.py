from __future__ import annotations

import pytest
from contextlib import asynccontextmanager
from uuid import uuid4

from app.database import Provider
from app.services.model_config_service import ModelConfigService
from app.services.providers import registry
from app.workers.context import ctx
from app.workers.tasks import _sync_provider_models


@pytest.fixture
async def sync_provider(db_session):
    provider = Provider(
        id=uuid4(),
        name="Test Celery Sync",
        provider_type="ollama",
        config={"base_url": "http://localhost"},
        is_active=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


class FakeSyncProvider:
    def get_capabilities(self):
        from app.services.providers.base import ProviderCapabilities

        return ProviderCapabilities(supports_model_sync=True)

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
async def test_sync_provider_models_preserves_manual_cost(db_session, sync_provider, monkeypatch):
    await ModelConfigService.create(
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
        return FakeSyncProvider()

    monkeypatch.setattr(registry, "create", fake_create)

    @asynccontextmanager
    async def fake_session_factory():
        yield db_session

    monkeypatch.setattr(ctx, "_session_factory", fake_session_factory)

    result = await _sync_provider_models("ollama")
    assert result["synced"] == 1

    config = await ModelConfigService.get_by_id(db_session, "llama3", sync_provider.id)
    assert config is not None
    assert config.cost_config["cost_per_1k_prompt_tokens"] == 0.01
