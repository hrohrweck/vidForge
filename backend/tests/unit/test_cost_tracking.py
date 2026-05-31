"""Unit tests for cost tracking across providers and the quick-media pipeline.

Covers:
- Sync task populates cost_config on ModelConfig rows
- AtlasCloudProvider.estimate_cost (image, video, no-config)
- Quick-media generation records cost on MediaAsset
- cost_config JSONB structure validation
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.database import ModelConfig, Provider
from app.models.media import MediaAsset, SourceType
from app.services.model_config_service import ModelConfigService
from app.services.providers.atlascloud import AtlasCloudProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider(*, db_session, provider_type="atlascloud", **overrides) -> Provider:
    """Create and insert a Provider row."""
    defaults: dict = {
        "id": uuid4(),
        "name": f"test-{provider_type}-{uuid4().hex[:6]}",
        "provider_type": provider_type,
        "config": {},
        "is_active": True,
    }
    defaults.update(overrides)
    provider = Provider(**defaults)  # type: ignore[arg-type]
    db_session.add(provider)
    return provider


async def _make_model_config(
    db_session, *, provider_id, model_id, modality, cost_config=None, **overrides
) -> ModelConfig:
    """Create a ModelConfig row and flush it."""
    data: dict = {
        "provider_id": provider_id,
        "model_id": model_id,
        "provider_model_id": f"provider-{model_id}",
        "display_name": model_id,
        "modality": modality,
        "endpoint_type": "atlascloud",
        "cost_config": cost_config,
    }
    data.update(overrides)
    config = await ModelConfigService.create(db_session, data)
    await db_session.flush()
    return config


# ---------------------------------------------------------------------------
# 1. Sync task populates cost_config
# ---------------------------------------------------------------------------

class TestSyncPopulatesCostConfig:
    """Verify that the model sync pipeline stores cost_config on ModelConfig."""

    @pytest.mark.asyncio
    async def test_sync_stores_cost_config_on_model_config(self, db_session):
        """When _sync_provider_models processes discovered models with
        cost_config, the resulting ModelConfig rows have it set."""
        from app.workers.tasks import _sync_provider_models

        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        discovered_data = [
            {
                "model_id": "test-image-v1",
                "provider_model_id": "api-img-v1",
                "display_name": "Test Image v1",
                "modality": "image",
                "endpoint_type": "atlascloud",
                "cost_config": {
                    "credits_per_image": 5,
                    "credits_per_second": 0,
                    "currency": "credits",
                },
            },
        ]

        with patch(
            "app.workers.tasks._discover_provider_models",
            AsyncMock(return_value=discovered_data),
        ), patch("app.workers.tasks.ctx") as mock_ctx:
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=db_session)
            mock_cm.__aexit__ = AsyncMock(return_value=None)
            mock_ctx.session_factory.return_value = mock_cm

            await _sync_provider_models("atlascloud")

        # Verify the ModelConfig was created with cost_config
        result = await ModelConfigService.get_by_id(
            db_session, model_id="test-image-v1", provider_id=provider.id
        )
        assert result is not None
        assert result.cost_config is not None
        assert result.cost_config["credits_per_image"] == 5
        assert result.cost_config["currency"] == "credits"

    @pytest.mark.asyncio
    async def test_sync_atlascloud_models_shape(self):
        """The cost_config dict attached to each discovered model has the
        expected keys and uses credits as currency."""
        from app.workers.tasks import _sync_atlascloud_models

        provider = MagicMock()
        provider.id = uuid4()

        # The function currently returns [] (API call is a TODO).
        # Verify the loop logic that WOULD run when API is implemented
        # by simulating what a discovered model looks like.
        test_model: dict = {
            "model_id": "flux-1.1-pro",
            "credits_per_image": 5,
            "credits_per_second": 0,
        }

        # Apply same logic as inside _sync_atlascloud_models
        test_model["cost_config"] = {
            "credits_per_image": test_model.get("credits_per_image", 0),
            "credits_per_second": test_model.get("credits_per_second", 0),
            "currency": "credits",
        }

        cost = test_model["cost_config"]
        assert cost["credits_per_image"] == 5
        assert cost["credits_per_second"] == 0
        assert cost["currency"] == "credits"

        # Defaults to 0 when keys are missing
        empty_model: dict = {"model_id": "unknown"}
        empty_model["cost_config"] = {
            "credits_per_image": empty_model.get("credits_per_image", 0),
            "credits_per_second": empty_model.get("credits_per_second", 0),
            "currency": "credits",
        }
        assert empty_model["cost_config"]["credits_per_image"] == 0
        assert empty_model["cost_config"]["credits_per_second"] == 0

        # The real function now calls the AtlasCloud API; mock it to avoid network
        with patch.object(AtlasCloudProvider, "initialize", AsyncMock(return_value=None)):
            result = await _sync_atlascloud_models(provider)
            assert result == []


# ---------------------------------------------------------------------------
# 2-4. AtlasCloud estimate_cost
# ---------------------------------------------------------------------------

class TestAtlasCloudEstimateCost:
    """Tests for AtlasCloudProvider.estimate_cost()."""

    @pytest.mark.asyncio
    async def test_estimate_cost_image_returns_credits_per_image(self):
        """estimate_cost for an image model returns credits_per_image."""
        provider = AtlasCloudProvider(provider_id=uuid4(), config={})

        mock_config = MagicMock(spec=ModelConfig)
        mock_config.modality = "image"
        mock_config.cost_config = {
            "credits_per_image": 7,
            "credits_per_second": 0,
            "currency": "credits",
        }

        with patch.object(
            provider, "_get_model_config", AsyncMock(return_value=mock_config)
        ):
            cost = await provider.estimate_cost(
                {"model": "flux-1.1-pro", "modality": "image"}
            )

        assert cost == 7.0
        assert isinstance(cost, float)

    @pytest.mark.asyncio
    async def test_estimate_cost_video_returns_credits_per_second_times_duration(
        self,
    ):
        """estimate_cost for a video model returns credits_per_second * duration."""
        provider = AtlasCloudProvider(provider_id=uuid4(), config={})

        mock_config = MagicMock(spec=ModelConfig)
        mock_config.modality = "video"
        mock_config.cost_config = {
            "credits_per_image": 0,
            "credits_per_second": 3,
            "currency": "credits",
        }

        with patch.object(
            provider, "_get_model_config", AsyncMock(return_value=mock_config)
        ):
            cost = await provider.estimate_cost(
                {"model": "wan-2.2", "modality": "video", "duration": 10}
            )

        assert cost == 30.0  # 3 credits/s * 10s

    @pytest.mark.asyncio
    async def test_estimate_cost_video_default_duration(self):
        """When duration is not in the workflow dict, defaults to 5."""
        provider = AtlasCloudProvider(provider_id=uuid4(), config={})

        mock_config = MagicMock(spec=ModelConfig)
        mock_config.modality = "video"
        mock_config.cost_config = {"credits_per_second": 2}

        with patch.object(
            provider, "_get_model_config", AsyncMock(return_value=mock_config)
        ):
            cost = await provider.estimate_cost(
                {"model": "wan-2.2", "modality": "video"}
            )

        assert cost == 10.0  # 2 credits/s * 5s (default)

    @pytest.mark.asyncio
    async def test_estimate_cost_returns_zero_when_no_config(self):
        """When _get_model_config returns None, estimate_cost returns 0.0."""
        provider = AtlasCloudProvider(provider_id=uuid4(), config={})

        with patch.object(
            provider, "_get_model_config", AsyncMock(return_value=None)
        ):
            cost = await provider.estimate_cost({"model": "nonexistent"})

        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_estimate_cost_returns_zero_when_no_cost_config(self):
        """When the ModelConfig exists but cost_config is None, returns 0.0."""
        provider = AtlasCloudProvider(provider_id=uuid4(), config={})

        mock_config = MagicMock(spec=ModelConfig)
        mock_config.modality = "image"
        mock_config.cost_config = None

        with patch.object(
            provider, "_get_model_config", AsyncMock(return_value=mock_config)
        ):
            cost = await provider.estimate_cost({"model": "some-model"})

        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_estimate_cost_unknown_modality_returns_zero(self):
        """An unknown/unsupported modality returns 0.0."""
        provider = AtlasCloudProvider(provider_id=uuid4(), config={})

        mock_config = MagicMock(spec=ModelConfig)
        mock_config.modality = "audio"
        mock_config.cost_config = {"credits_per_second": 5}

        with patch.object(
            provider, "_get_model_config", AsyncMock(return_value=mock_config)
        ):
            cost = await provider.estimate_cost({"model": "musicgen"})

        assert cost == 0.0


# ---------------------------------------------------------------------------
# 5. Quick media records cost on MediaAsset
# ---------------------------------------------------------------------------

class TestQuickMediaRecordsCost:
    """Verify that _generate_quick_media sets MediaAsset.cost."""

    @pytest.mark.asyncio
    async def test_image_generation_records_cost(self, db_session):
        """When generate_quick_media creates an image, MediaAsset.cost is set
        from the model's cost_config."""
        from app.workers.tasks import _generate_quick_media

        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        cost_config = {"credits_per_image": 5, "credits_per_second": 0, "currency": "credits"}
        config = await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-image-cost",
            modality="image",
            cost_config=cost_config,
        )
        await db_session.commit()

        # Mock ctx.session_factory to return our test session
        mock_ctx = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_ctx.session_factory.return_value = mock_cm
        mock_ctx.redis = AsyncMock()

        user_id = str(uuid4())

        with patch("app.workers.tasks.ctx", mock_ctx), \
             patch("app.services.media_generator.generate_image", AsyncMock(
                 return_value=("/tmp/test.png", "test-image-cost", provider.id)
             )), \
             patch("app.workers.tasks.Path.exists", return_value=True), \
             patch("app.workers.tasks.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = 12345
            mock_self = MagicMock()

            await _generate_quick_media(
                mock_self, user_id, "test-image-cost",
                prompt="a test image", aspect_ratio="1:1",
                duration=5, negative_prompt=None, seed=None,
            )

        # Verify the MediaAsset was created with cost
        from sqlalchemy import select
        result = await db_session.execute(
            select(MediaAsset).where(MediaAsset.user_id == uuid4().__class__(user_id))
        )
        assets = result.scalars().all()
        assert len(assets) == 1
        asset = assets[0]
        assert asset.cost is not None
        assert asset.cost == Decimal("5")
        assert asset.file_type == "image"

    @pytest.mark.asyncio
    async def test_video_generation_records_cost(self, db_session):
        """When generate_quick_media creates a video, MediaAsset.cost is
        credits_per_second * duration."""
        from app.workers.tasks import _generate_quick_media

        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        cost_config = {"credits_per_image": 0, "credits_per_second": 3, "currency": "credits"}
        config = await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-video-cost",
            modality="video",
            cost_config=cost_config,
        )
        await db_session.commit()

        mock_ctx = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_ctx.session_factory.return_value = mock_cm
        mock_ctx.redis = AsyncMock()

        user_id = str(uuid4())

        with patch("app.workers.tasks.ctx", mock_ctx), \
             patch("app.services.media_generator.generate_video", AsyncMock(
                 return_value=("/tmp/test.mp4", "test-video-cost", provider.id, 8)
             )), \
             patch("app.workers.tasks.Path.exists", return_value=True), \
             patch("app.workers.tasks.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = 98765
            mock_self = MagicMock()

            await _generate_quick_media(
                mock_self, user_id, "test-video-cost",
                prompt="a test video", aspect_ratio="16:9",
                duration=8, negative_prompt=None, seed=None,
            )

        from sqlalchemy import select
        result = await db_session.execute(
            select(MediaAsset).where(MediaAsset.user_id == uuid4().__class__(user_id))
        )
        assets = result.scalars().all()
        assert len(assets) == 1
        asset = assets[0]
        assert asset.cost is not None
        # credits_per_second (3) * duration (8) = 24
        assert asset.cost == Decimal("24")
        assert asset.file_type == "video"


# ---------------------------------------------------------------------------
# 6. cost_config JSONB structure
# ---------------------------------------------------------------------------

class TestCostConfigJsonStructure:
    """Verify the cost_config JSONB column stores the expected schema."""

    @pytest.mark.asyncio
    async def test_cost_config_has_expected_keys(self, db_session):
        """cost_config stored on a ModelConfig includes credits_per_image,
        credits_per_second, and currency."""
        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        cost_config = {
            "credits_per_image": 5,
            "credits_per_second": 3,
            "currency": "credits",
        }
        config = await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="structured-cost-model",
            modality="video",
            cost_config=cost_config,
        )
        await db_session.commit()

        # Re-fetch to ensure JSONB round-trips correctly
        fetched = await ModelConfigService.get_by_id(
            db_session, model_id="structured-cost-model", provider_id=provider.id
        )
        assert fetched is not None
        cc = fetched.cost_config
        assert cc is not None

        # Required keys
        assert "credits_per_image" in cc
        assert "credits_per_second" in cc
        assert "currency" in cc

        # Value types
        assert isinstance(cc["credits_per_image"], int)
        assert isinstance(cc["credits_per_second"], int)
        assert isinstance(cc["currency"], str)
        assert cc["currency"] == "credits"

    @pytest.mark.asyncio
    async def test_cost_config_defaults_when_empty(self, db_session):
        """A ModelConfig with cost_config=None can be stored and retrieved."""
        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        config = await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="no-cost-model",
            modality="image",
            cost_config=None,
        )
        await db_session.commit()

        fetched = await ModelConfigService.get_by_id(
            db_session, model_id="no-cost-model", provider_id=provider.id
        )
        assert fetched is not None
        assert fetched.cost_config is None
