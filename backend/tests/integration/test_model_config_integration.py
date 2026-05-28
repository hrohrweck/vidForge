"""Integration tests for ModelConfig → provider payload flow.

Tests the full pipeline: model config stored in DB → build_payload()
constructs provider-ready payload with correct parameter mapping.
Also covers deprecated model warnings and immediate-update behavior.

Requires PostgreSQL (integration test suite).  No external API calls.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from app.database import ModelConfig, Provider
from app.services.model_config_service import ModelConfigService


@pytest.fixture
async def video_provider(db_session):
    """Create a minimal Provider row for FK constraint."""
    provider = Provider(
        id=uuid4(),
        name="test-video-provider",
        provider_type="comfyui_direct",
        config={"base_url": "http://localhost:8188"},
    )
    db_session.add(provider)
    await db_session.flush()
    return provider


@pytest.fixture
async def video_model(db_session, video_provider):
    """Create a video ModelConfig with a parameter_map."""
    data = {
        "provider_id": video_provider.id,
        "model_id": "wan22-video",
        "provider_model_id": "wan22-provider-id",
        "display_name": "Wan 2.2 Video",
        "modality": "video",
        "endpoint_type": "comfyui",
        "parameter_map": {"aspect_ratio": "aspect", "duration": "seconds"},
        "extra_params": {"steps": 30, "fps": 16},
    }
    return await ModelConfigService.create(db_session, data)


# ---------------------------------------------------------------------------
# build_payload – parameter mapping & construction
# ---------------------------------------------------------------------------


class TestBuildPayloadParameterMapping:
    """Integration: parameter_map stored in DB → build_payload translates keys."""

    async def test_payload_maps_parameter_keys(self, db_session, video_model):
        """Keys in kwargs are mapped via parameter_map to provider keys."""
        payload = video_model.build_payload(
            prompt="a test video",
            aspect_ratio="16:9",
            duration=10,
        )

        # Original keys should NOT be in payload
        assert "aspect_ratio" not in payload
        assert "duration" not in payload

        # Mapped keys should be present with correct values
        assert payload["aspect"] == "16:9"
        assert payload["seconds"] == 10
        assert payload["prompt"] == "a test video"

    async def test_payload_includes_provider_model_id(self, db_session, video_model):
        """build_payload always adds the provider_model_id as 'model'."""
        payload = video_model.build_payload(prompt="test")

        assert payload["model"] == video_model.provider_model_id

    async def test_payload_merges_extra_params(self, db_session, video_model):
        """extra_params are included as defaults unless overridden by kwargs."""
        payload = video_model.build_payload(prompt="test")

        assert payload["steps"] == 30
        assert payload["fps"] == 16

    async def test_extra_params_do_not_override_kwargs(self, db_session, video_model):
        """Kwargs always take precedence over extra_params defaults."""
        payload = video_model.build_payload(
            prompt="test", steps=75, fps=24
        )

        assert payload["steps"] == 75
        assert payload["fps"] == 24
        # From extra_params via mapping, should still be included
        assert "model" in payload


class TestPayloadWithMultipleModels:
    """Two ModelConfigs with different parameter_maps coexist correctly."""

    async def test_different_parameter_maps_produce_different_payloads(
        self, db_session, video_provider
    ):
        """Each model's parameter_map is isolated."""
        # Model A maps aspect_ratio → aspect
        model_a = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "model-a",
                "provider_model_id": "pm-a",
                "display_name": "Model A",
                "modality": "video",
                "endpoint_type": "comfyui",
                "parameter_map": {"aspect_ratio": "aspect"},
            },
        )
        # Model B maps aspect_ratio → ratio
        model_b = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "model-b",
                "provider_model_id": "pm-b",
                "display_name": "Model B",
                "modality": "video",
                "endpoint_type": "comfyui",
                "parameter_map": {"aspect_ratio": "ratio"},
            },
        )

        payload_a = model_a.build_payload(prompt="test", aspect_ratio="16:9")
        payload_b = model_b.build_payload(prompt="test", aspect_ratio="16:9")

        assert payload_a["aspect"] == "16:9"
        assert "aspect" not in payload_b
        assert payload_b["ratio"] == "16:9"
        assert "ratio" not in payload_a


# ---------------------------------------------------------------------------
# Prompt format handling
# ---------------------------------------------------------------------------


class TestPromptFormat:
    """prompt_format='array' converts string prompts to list."""

    async def test_array_prompt_format(self, db_session, video_provider):
        model = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "array-model",
                "provider_model_id": "pm-array",
                "display_name": "Array Prompt",
                "modality": "image",
                "endpoint_type": "comfyui",
                "prompt_format": "array",
            },
        )

        payload = model.build_payload(prompt="a flower in bloom")
        assert payload["prompt"] == ["a flower in bloom"]

    async def test_string_prompt_format_default(self, db_session, video_provider):
        model = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "string-model",
                "provider_model_id": "pm-string",
                "display_name": "String Prompt",
                "modality": "image",
                "endpoint_type": "comfyui",
            },
        )

        payload = model.build_payload(prompt="a mountain landscape")
        assert isinstance(payload["prompt"], str)
        assert payload["prompt"] == "a mountain landscape"


# ---------------------------------------------------------------------------
# Deprecated model behavior
# ---------------------------------------------------------------------------


class TestDeprecatedModelWarning:
    """get_or_create() logs a warning when using a deprecated model."""

    async def test_deprecated_model_logs_warning(
        self, db_session, video_provider, caplog
    ):
        """Accessing a deprecated model via get_or_create emits a warning."""
        model = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "old-video-model",
                "provider_model_id": "pm-old",
                "display_name": "Old Video Model",
                "modality": "video",
                "endpoint_type": "comfyui",
                "is_deprecated": True,
            },
        )

        with caplog.at_level(logging.WARNING):
            result = await ModelConfigService.get_or_create(
                db_session,
                provider_id=video_provider.id,
                model_id="old-video-model",
                defaults={},
            )

        assert result is not None
        assert result.model_id == "old-video-model"

        warning_messages = [r.message for r in caplog.records]
        assert any(
            "deprecated" in msg.lower() and "old-video-model" in msg
            for msg in warning_messages
        )

    async def test_deprecated_model_build_payload_still_works(
        self, db_session, video_provider
    ):
        """Even deprecated models produce valid payloads."""
        model = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "deprecated-video",
                "provider_model_id": "pm-dep",
                "display_name": "Deprecated Video",
                "modality": "video",
                "endpoint_type": "comfyui",
                "is_deprecated": True,
                "parameter_map": {"resolution": "size"},
            },
        )

        payload = model.build_payload(prompt="test", resolution="1080p")
        assert payload["size"] == "1080p"
        assert payload["model"] == "pm-dep"


# ---------------------------------------------------------------------------
# Model config update takes effect immediately
# ---------------------------------------------------------------------------


class TestConfigUpdateImmediate:
    """Updates to ModelConfig (parameter_map, extra_params, etc.) are
    reflected in build_payload without any cache invalidation delay."""

    async def test_parameter_map_update_reflected_immediately(
        self, db_session, video_model
    ):
        """Changing parameter_map changes build_payload output immediately."""
        payload_before = video_model.build_payload(
            prompt="test", aspect_ratio="16:9", duration=5
        )
        assert payload_before["aspect"] == "16:9"
        assert payload_before["seconds"] == 5

        await ModelConfigService.update(
            db_session,
            video_model.model_id,
            video_model.provider_id,
            {"parameter_map": {"aspect_ratio": "target_aspect", "foo": "bar"}},
        )
        await db_session.refresh(video_model)

        payload_after = video_model.build_payload(
            prompt="test", aspect_ratio="21:9", foo=42
        )
        assert "aspect" not in payload_after
        assert "seconds" not in payload_after
        assert payload_after["target_aspect"] == "21:9"
        assert payload_after["bar"] == 42

    async def test_extra_params_update_reflected_immediately(
        self, db_session, video_model
    ):
        """Changing extra_params changes build_payload defaults immediately."""
        payload_before = video_model.build_payload(prompt="test")
        assert payload_before["steps"] == 30

        await ModelConfigService.update(
            db_session,
            video_model.model_id,
            video_model.provider_id,
            {"extra_params": {"cfg": 12.0}},
        )
        await db_session.refresh(video_model)

        payload_after = video_model.build_payload(prompt="test")
        assert "steps" not in payload_after  # old params gone
        assert payload_after["cfg"] == 12.0  # new param present

    async def test_display_name_update_persists(self, db_session, video_model):
        """Non-payload fields also update correctly."""
        from app.database import ModelConfig

        await ModelConfigService.update(
            db_session,
            video_model.model_id,
            video_model.provider_id,
            {"display_name": "Wan 2.2 Updated"},
        )
        await db_session.refresh(video_model)

        # Re-fetch from DB to verify persistence
        fetched = await ModelConfigService.get_by_id(
            db_session, video_model.model_id, video_model.provider_id
        )
        assert fetched is not None
        assert fetched.display_name == "Wan 2.2 Updated"

    async def test_mark_deprecated_then_check(self, db_session, video_model):
        """mark_deprecated sets both is_deprecated and is_active."""
        assert video_model.is_deprecated is False
        assert video_model.is_active is True

        await ModelConfigService.mark_deprecated(
            db_session, video_model.model_id, video_model.provider_id
        )
        await db_session.refresh(video_model)

        assert video_model.is_deprecated is True
        assert video_model.is_active is False

        active = await ModelConfigService.list_by_provider(
            db_session, video_model.provider_id, active_only=True
        )
        assert all(m.model_id != video_model.model_id for m in active)

        all_models = await ModelConfigService.list_by_provider(
            db_session, video_model.provider_id, active_only=False
        )
        assert any(m.model_id == video_model.model_id for m in all_models)


# ---------------------------------------------------------------------------
# Provider dispatch simulation (no external API)
# ---------------------------------------------------------------------------


class TestProviderDispatchSimulation:
    """Simulate provider dispatch: correct model + payload sent per modality."""

    async def test_video_model_payload_for_video_provider(
        self, db_session, video_provider
    ):
        """Payload built for video modality has expected structure."""
        model = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "dispatch-video",
                "provider_model_id": "vid-42",
                "display_name": "Dispatch Video",
                "modality": "video",
                "endpoint_type": "comfyui",
                "parameter_map": {"width": "w", "height": "h", "duration": "duration"},
                "extra_params": {"fps": 16},
            },
        )

        payload = model.build_payload(
            prompt="sunset time-lapse", width=848, height=480, duration=5
        )

        assert payload == {
            "prompt": "sunset time-lapse",
            "w": 848,
            "h": 480,
            "duration": 5,
            "fps": 16,
            "model": "vid-42",
        }

    async def test_image_model_payload_for_image_provider(
        self, db_session, video_provider
    ):
        """Payload built for image modality is correctly structured."""
        model = await ModelConfigService.create(
            db_session,
            {
                "provider_id": video_provider.id,
                "model_id": "dispatch-image",
                "provider_model_id": "img-99",
                "display_name": "Dispatch Image",
                "modality": "image",
                "endpoint_type": "comfyui",
                "parameter_map": {"aspect_ratio": "aspect", "num_images": "n"},
                "extra_params": {"cfg": 7.5, "steps": 25},
            },
        )

        payload = model.build_payload(
            prompt="cyberpunk city", aspect_ratio="1:1", num_images=4
        )

        assert payload == {
            "prompt": "cyberpunk city",
            "aspect": "1:1",
            "n": 4,
            "cfg": 7.5,
            "steps": 25,
            "model": "img-99",
        }
