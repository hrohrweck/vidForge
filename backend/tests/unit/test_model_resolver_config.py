from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import ModelConfig, Provider
from app.services.model_config_service import ModelConfigService


async def _provider(
    db: AsyncSession,
    *,
    provider_type: str = "atlascloud",
    name: str | None = None,
    is_active: bool = True,
) -> Provider:
    provider = Provider(
        id=uuid4(),
        name=name or f"{provider_type}-{uuid4()}",
        provider_type=provider_type,
        config={},
        is_active=is_active,
    )
    db.add(provider)
    await db.flush()
    return provider


async def _model(
    db: AsyncSession,
    provider: Provider,
    *,
    model_id: str,
    provider_model_id: str | None = None,
    modality: str = "video",
    is_active: bool = True,
) -> ModelConfig:
    config = await ModelConfigService.create(
        db,
        {
            "provider_id": provider.id,
            "model_id": model_id,
            "provider_model_id": provider_model_id or model_id,
            "display_name": model_id,
            "modality": modality,
            "endpoint_type": "generateVideo",
            "is_active": is_active,
        },
    )
    await db.flush()
    return config


class TestResolveModelConfig:
    async def test_exact_model_id_and_provider_id_returns_without_warning(
        self, db_session, caplog
    ):
        provider = await _provider(db_session)
        config = await _model(db_session, provider, model_id="atlascloud/wan/video")

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "atlascloud/wan/video", provider.id
            )

        assert resolved == config
        assert "Legacy model reference resolved" not in caplog.text

    async def test_provider_model_id_fallback_logs_warning(self, db_session, caplog):
        provider = await _provider(db_session)
        config = await _model(
            db_session,
            provider,
            model_id="atlascloud/wan-2.2-turbo/image-to-video",
            provider_model_id="wan-2.2-turbo/image-to-video",
        )

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "wan-2.2-turbo/image-to-video", provider.id
            )

        assert resolved == config
        assert "Legacy model reference resolved" in caplog.text
        assert "wan-2.2-turbo/image-to-video" in caplog.text

    async def test_legacy_prefix_stripped_then_model_id_retried(self, db_session, caplog):
        provider = await _provider(db_session, provider_type="poe")
        config = await _model(db_session, provider, model_id="grok-imagine-video")

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "poe:grok-imagine-video", provider.id
            )

        assert resolved == config
        assert "input=poe:grok-imagine-video -> model_id=grok-imagine-video" in caplog.text

    async def test_legacy_prefix_stripped_then_provider_model_id_retried(
        self, db_session, caplog
    ):
        provider = await _provider(db_session, provider_type="poe")
        config = await _model(
            db_session,
            provider,
            model_id="grok-imagine-video-v2",
            provider_model_id="grok-imagine-video",
        )

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "poe:grok-imagine-video", provider.id
            )

        assert resolved == config
        assert "model_id=grok-imagine-video-v2" in caplog.text

    async def test_atlascloud_prefix_context_repairs_model_id(self, db_session, caplog):
        provider = await _provider(db_session, provider_type="atlascloud")
        config = await _model(db_session, provider, model_id="atlascloud/wan-2.2-turbo")

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "atlascloud:wan-2.2-turbo", provider.id
            )

        assert resolved == config
        assert "input=atlascloud:wan-2.2-turbo -> model_id=atlascloud/wan-2.2-turbo" in caplog.text

    async def test_atlascloud_provider_context_repairs_bare_model_id(self, db_session, caplog):
        provider = await _provider(db_session, provider_type="atlascloud")
        config = await _model(db_session, provider, model_id="atlascloud/wan-2.2-turbo")

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "wan-2.2-turbo", provider.id
            )

        assert resolved == config
        assert "input=wan-2.2-turbo -> model_id=atlascloud/wan-2.2-turbo" in caplog.text

    async def test_unique_suffix_match_resolves(self, db_session, caplog):
        provider = await _provider(db_session, provider_type="atlascloud")
        config = await _model(
            db_session,
            provider,
            model_id="xai/grok-imagine-video/image-to-video",
        )

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "grok-imagine-video/image-to-video", provider.id
            )

        assert resolved == config
        assert "model_id=xai/grok-imagine-video/image-to-video" in caplog.text

    async def test_suffix_match_rejects_ambiguous_matches(self, db_session, caplog):
        provider = await _provider(db_session, provider_type="atlascloud")
        await _model(db_session, provider, model_id="xai/grok-imagine-video/image-to-video")
        await _model(db_session, provider, model_id="poe/grok-imagine-video/image-to-video")

        with caplog.at_level(logging.WARNING):
            resolved = await ModelConfigService.resolve_model_config(
                db_session, "grok-imagine-video/image-to-video", provider.id
            )

        assert resolved is None
        assert "Legacy model reference resolved" not in caplog.text

    async def test_provider_id_none_requires_unique_active_model_match(self, db_session):
        atlascloud = await _provider(db_session, provider_type="atlascloud")
        poe = await _provider(db_session, provider_type="poe")
        config = await _model(db_session, atlascloud, model_id="unique-model")
        await _model(db_session, poe, model_id="inactive-unique-model", is_active=False)

        resolved = await ModelConfigService.resolve_model_config(db_session, "unique-model")

        assert resolved == config

    async def test_provider_id_none_rejects_ambiguous_active_model_matches(self, db_session):
        atlascloud = await _provider(db_session, provider_type="atlascloud")
        poe = await _provider(db_session, provider_type="poe")
        await _model(db_session, atlascloud, model_id="shared-model")
        await _model(db_session, poe, model_id="shared-model")

        resolved = await ModelConfigService.resolve_model_config(db_session, "shared-model")

        assert resolved is None

    async def test_provider_id_none_legacy_prefix_limits_provider_context(self, db_session):
        atlascloud = await _provider(db_session, provider_type="atlascloud")
        poe = await _provider(db_session, provider_type="poe")
        config = await _model(db_session, atlascloud, model_id="shared-model")
        await _model(db_session, poe, model_id="shared-model")

        resolved = await ModelConfigService.resolve_model_config(
            db_session, "atlascloud:shared-model"
        )

        assert resolved == config

    async def test_modality_filter_applies_to_resolution(self, db_session):
        provider = await _provider(db_session)
        await _model(db_session, provider, model_id="atlascloud/wan", modality="video")

        resolved = await ModelConfigService.resolve_model_config(
            db_session, "atlascloud/wan", provider.id, modality="image"
        )

        assert resolved is None

    async def test_returns_none_when_no_branch_matches(self, db_session):
        provider = await _provider(db_session)

        resolved = await ModelConfigService.resolve_model_config(
            db_session, "missing-model", provider.id
        )

        assert resolved is None
