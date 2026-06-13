from __future__ import annotations

import pytest
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.services.model_config_service import ModelConfigService
from app.database import ModelConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROVIDER_ID = uuid4()


def _make_data(**overrides) -> dict:
    """Return a minimal valid ModelConfig creation dict."""
    defaults = {
        "provider_id": PROVIDER_ID,
        "model_id": "test-model-1",
        "provider_model_id": "some-model-id",
        "display_name": "Test Model",
        "modality": "image",
        "endpoint_type": "comfyui",
        "is_active": True,
    }
    defaults.update(overrides)
    return defaults


async def _create(db, **overrides) -> ModelConfig:
    return await ModelConfigService.create(db, _make_data(**overrides))


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------

class TestCreateAndGet:
    async def test_create_and_get_by_id(self, db_session):
        config = await _create(db_session)
        fetched = await ModelConfigService.get_by_id(
            db_session, config.model_id, config.provider_id
        )
        assert fetched is not None
        assert fetched.id == config.id
        assert fetched.model_id == "test-model-1"

    async def test_get_by_id_returns_none_for_missing(self, db_session):
        result = await ModelConfigService.get_by_id(
            db_session, "nonexistent", PROVIDER_ID
        )
        assert result is None


class TestListByProvider:
    async def test_list_by_provider_returns_all(self, db_session):
        await _create(db_session, model_id="m1", display_name="M1")
        await _create(db_session, model_id="m2", display_name="M2")
        results = await ModelConfigService.list_by_provider(db_session, PROVIDER_ID)
        assert len(results) == 2

    async def test_list_by_provider_modality_filter(self, db_session):
        await _create(db_session, model_id="img", modality="image")
        await _create(db_session, model_id="vid", modality="video")
        results = await ModelConfigService.list_by_provider(
            db_session, PROVIDER_ID, modality="video"
        )
        assert len(results) == 1
        assert results[0].model_id == "vid"

    async def test_list_by_provider_excludes_inactive(self, db_session):
        c1 = await _create(db_session, model_id="active")
        c2 = await _create(db_session, model_id="inactive", is_active=False)
        results = await ModelConfigService.list_by_provider(db_session, PROVIDER_ID)
        assert len(results) == 1
        assert results[0].model_id == "active"

    async def test_list_by_provider_include_inactive_when_active_only_false(self, db_session):
        await _create(db_session, model_id="active")
        await _create(db_session, model_id="inactive", is_active=False)
        results = await ModelConfigService.list_by_provider(
            db_session, PROVIDER_ID, active_only=False
        )
        assert len(results) == 2


class TestListByModality:
    async def test_list_by_modality_cross_provider(self, db_session):
        p2 = uuid4()
        await _create(db_session, model_id="img1", modality="image")
        await _create(db_session, model_id="img2", modality="image", provider_id=p2)
        results = await ModelConfigService.list_by_modality(db_session, "image")
        assert len(results) == 2


class TestUpdate:
    async def test_update_partial(self, db_session):
        config = await _create(
            db_session, display_name="Original", prompt_format="string"
        )
        updated = await ModelConfigService.update(
            db_session,
            config.model_id,
            config.provider_id,
            {"display_name": "Updated"},
        )
        assert updated.display_name == "Updated"
        # Other fields unchanged
        assert updated.prompt_format == "string"
        assert updated.modality == "image"

    async def test_update_raises_on_missing(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            await ModelConfigService.update(
                db_session, "ghost", PROVIDER_ID, {"display_name": "X"}
            )


class TestDelete:
    async def test_delete_soft(self, db_session):
        config = await _create(db_session, is_active=True)
        await ModelConfigService.delete(
            db_session, config.model_id, config.provider_id
        )
        # get_by_id still returns the row (soft-delete)
        fetched = await ModelConfigService.get_by_id(
            db_session, config.model_id, config.provider_id
        )
        assert fetched is not None
        assert fetched.is_active is False

    async def test_delete_nonexistent_is_noop(self, db_session):
        # Should not raise
        await ModelConfigService.delete(db_session, "ghost", PROVIDER_ID)


class TestMarkDeprecated:
    async def test_mark_deprecated_sets_flags(self, db_session):
        config = await _create(db_session)
        await ModelConfigService.mark_deprecated(
            db_session, config.model_id, config.provider_id
        )
        fetched = await ModelConfigService.get_by_id(
            db_session, config.model_id, config.provider_id
        )
        assert fetched is not None
        assert fetched.is_deprecated is True
        assert fetched.is_active is False

    async def test_mark_deprecated_raises_on_missing(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            await ModelConfigService.mark_deprecated(
                db_session, "ghost", PROVIDER_ID
            )


class TestGetOrCreate:
    async def test_get_or_create_returns_existing(self, db_session):
        existing = await _create(db_session, display_name="Exists")
        result = await ModelConfigService.get_or_create(
            db_session, PROVIDER_ID, "test-model-1",
            {"display_name": "Should Not Be Used"},
        )
        assert result.id == existing.id
        assert result.display_name == "Exists"

    async def test_get_or_create_creates_when_missing(self, db_session):
        result = await ModelConfigService.get_or_create(
            db_session, PROVIDER_ID, "new-model",
            {"display_name": "New Model", "modality": "video"},
        )
        assert result.model_id == "new-model"
        assert result.display_name == "New Model"
        assert result.modality == "video"

    async def test_get_or_create_new_model_is_inactive(self, db_session):
        """New model created via get_or_create defaults to is_active=False."""
        result = await ModelConfigService.get_or_create(
            db_session, PROVIDER_ID, "brand-new-model",
            {"display_name": "Brand New"},
        )
        assert result.is_active is False

    async def test_get_or_create_existing_active_stays_active(self, db_session):
        """Existing model with is_active=True keeps its state."""
        existing = await ModelConfigService.create(
            db_session,
            _make_data(is_active=True, model_id="active-kept"),
        )
        result = await ModelConfigService.get_or_create(
            db_session, PROVIDER_ID, "active-kept",
            {"display_name": "Should Not Change"},
        )
        assert result.id == existing.id
        assert result.is_active is True

    async def test_get_or_create_existing_inactive_stays_inactive(self, db_session):
        """Existing model with is_active=False keeps its state."""
        existing = await ModelConfigService.create(
            db_session,
            _make_data(is_active=False, model_id="inactive-kept"),
        )
        result = await ModelConfigService.get_or_create(
            db_session, PROVIDER_ID, "inactive-kept",
            {"display_name": "Should Not Change"},
        )
        assert result.id == existing.id
        assert result.is_active is False


# ---------------------------------------------------------------------------
# build_payload Tests
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_build_payload_string_prompt(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
        )
        payload = config.build_payload(prompt="a beautiful sunset")
        assert payload["prompt"] == "a beautiful sunset"

    def test_build_payload_array_prompt(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
            prompt_format="array",
        )
        payload = config.build_payload(prompt="a beautiful sunset")
        assert payload["prompt"] == ["a beautiful sunset"]

    def test_build_payload_parameter_map(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
            parameter_map={"aspect_ratio": "aspect"},
        )
        payload = config.build_payload(aspect_ratio="16:9")
        assert "aspect_ratio" not in payload
        assert payload["aspect"] == "16:9"

    def test_build_payload_extra_params_merged(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
            extra_params={"steps": 30, "cfg": 7.5},
        )
        payload = config.build_payload(prompt="test")
        assert payload["steps"] == 30
        assert payload["cfg"] == 7.5

    def test_build_payload_extra_params_do_not_override(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
            extra_params={"steps": 30},
        )
        payload = config.build_payload(prompt="test", steps=50)
        # kwargs take precedence over extra_params
        assert payload["steps"] == 50

    def test_build_payload_includes_model_id(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="my-provider-model-42",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
        )
        payload = config.build_payload()
        assert payload["model"] == "my-provider-model-42"


# ---------------------------------------------------------------------------
# supports Tests
# ---------------------------------------------------------------------------

class TestSupports:
    def test_supports_returns_true_for_capability(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="video",
            endpoint_type="comfyui",
            capabilities={"supports_t2v": True, "supports_i2v": True},
        )
        assert config.supports("supports_t2v") is True

    def test_supports_returns_false_for_missing_capability(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
            capabilities={"supports_t2v": True},
        )
        assert config.supports("supports_i2v") is False

    def test_supports_with_null_capabilities(self):
        config = ModelConfig(
            provider_id=PROVIDER_ID,
            model_id="m1",
            provider_model_id="pm1",
            display_name="Test",
            modality="image",
            endpoint_type="comfyui",
            capabilities=None,
        )
        assert config.supports("anything") is False


# ---------------------------------------------------------------------------
# Constraint Tests
# ---------------------------------------------------------------------------

class TestUniqueConstraint:
    async def test_unique_constraint_raises_integrity_error(self, db_session):
        await _create(db_session, model_id="dup")
        with pytest.raises(IntegrityError):
            await _create(db_session, model_id="dup")


# ---------------------------------------------------------------------------
# Upsert Tests
# ---------------------------------------------------------------------------

class TestUpsert:
    async def test_upsert_creates_missing_config(self, db_session):
        config = await ModelConfigService.upsert(
            db_session,
            PROVIDER_ID,
            "upsert-new",
            {
                "display_name": "Upsert New",
                "provider_model_id": "upsert-new",
                "modality": "image",
                "endpoint_type": "generateImage",
                "cost_config": {"cost_per_image": 0.05, "currency": "USD"},
            },
        )
        assert config.model_id == "upsert-new"
        assert config.is_active is False
        assert config.cost_config["cost_per_image"] == 0.05

    async def test_upsert_merges_cost_config(self, db_session):
        await _create(
            db_session,
            model_id="upsert-merge",
            cost_config={"cost_per_image": 0.05, "currency": "USD"},
        )

        config = await ModelConfigService.upsert(
            db_session,
            PROVIDER_ID,
            "upsert-merge",
            {
                "display_name": "Updated",
                "modality": "image",
                "endpoint_type": "generateImage",
                "cost_config": {"currency": "credits"},
            },
        )
        await db_session.commit()

        assert config.display_name == "Updated"
        assert config.cost_config["cost_per_image"] == 0.05
        assert config.cost_config["currency"] == "credits"

    async def test_upsert_overwrites_when_provider_returns_value(self, db_session):
        await _create(
            db_session,
            model_id="upsert-overwrite",
            cost_config={"cost_per_image": 0.05, "currency": "USD"},
        )

        config = await ModelConfigService.upsert(
            db_session,
            PROVIDER_ID,
            "upsert-overwrite",
            {
                "display_name": "Updated",
                "modality": "image",
                "endpoint_type": "generateImage",
                "cost_config": {"cost_per_image": 0.10, "currency": "credits"},
            },
        )
        await db_session.commit()

        assert config.cost_config["cost_per_image"] == 0.10
        assert config.cost_config["currency"] == "credits"
