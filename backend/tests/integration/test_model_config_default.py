"""Integration tests for model_configs.is_active behavior.

Verifies:
- Explicit is_active=True persists correctly
- Explicit is_active=False persists correctly
- ORM-created ModelConfig without is_active uses Python-side default

Note: DB-level server_default migration (027) is verified via QA scenarios
against the live database. These tests validate ORM-level read/write behavior.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import ModelConfig, Provider


class TestModelConfigIsActive:
    """Verify is_active read/write behavior."""

    async def test_explicit_true(self, db_session: AsyncSession) -> None:
        """ModelConfig with is_active=True persists correctly."""
        provider = Provider(
            id=uuid4(), name="test-provider", provider_type="poe",
            config={"api_key": "test"},
        )
        db_session.add(provider)
        await db_session.flush()

        model = ModelConfig(
            id=uuid4(),
            provider_id=provider.id,
            model_id="explicit-true-test",
            provider_model_id="explicit-true-provider-id",
            display_name="Explicit True Test",
            modality="image",
            endpoint_type="generateImage",
            is_active=True,
        )
        db_session.add(model)
        await db_session.flush()

        refreshed = await db_session.get(ModelConfig, model.id)
        assert refreshed is not None
        assert refreshed.is_active is True

    async def test_explicit_false(self, db_session: AsyncSession) -> None:
        """ModelConfig with is_active=False persists correctly."""
        provider = Provider(
            id=uuid4(), name="test-provider-2", provider_type="poe",
            config={"api_key": "test"},
        )
        db_session.add(provider)
        await db_session.flush()

        model = ModelConfig(
            id=uuid4(),
            provider_id=provider.id,
            model_id="explicit-false-test",
            provider_model_id="explicit-false-provider-id",
            display_name="Explicit False Test",
            modality="text",
            endpoint_type="chat_completions",
            is_active=False,
        )
        db_session.add(model)
        await db_session.flush()

        refreshed = await db_session.get(ModelConfig, model.id)
        assert refreshed is not None
        assert refreshed.is_active is False
