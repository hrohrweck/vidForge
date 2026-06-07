"""Unit tests for the /api/models endpoints.

Covers:
- Disabled (is_active=False) models excluded from /available response
- capabilities field present in API response
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import ModelConfig, Provider

# ── Helpers ──────────────────────────────────────────────────────────


async def _create_provider(db_session, **overrides) -> Provider:
    """Create a minimal Provider for FK constraints."""
    defaults = {
        "name": f"test-provider-{uuid4().hex[:8]}",
        "provider_type": "comfyui_direct",
        "config": {"base_url": "http://localhost:8188"},
    }
    defaults.update(overrides)
    provider = Provider(id=uuid4(), **defaults)
    db_session.add(provider)
    await db_session.flush()
    return provider


async def _create_model(db_session, provider: Provider, **overrides) -> ModelConfig:
    """Create a ModelConfig row with sensible defaults for testing."""
    defaults = {
        "provider_id": provider.id,
        "model_id": f"test-model-{uuid4().hex[:8]}",
        "provider_model_id": f"provider-model-{uuid4().hex[:8]}",
        "display_name": "Test Model",
        "modality": "image",
        "endpoint_type": "comfyui",
        "is_active": True,
    }
    defaults.update(overrides)
    model = ModelConfig(id=uuid4(), **defaults)
    db_session.add(model)
    await db_session.flush()
    return model


# ── Disabled model filtering ─────────────────────────────────────────


class TestDisabledModelFiltering:
    """is_active=False models must not appear in API responses."""

    @pytest.mark.asyncio
    async def test_disabled_model_not_in_available(self, client: AsyncClient, db_session):
        """Only active models appear in /api/models/available."""
        provider = await _create_provider(db_session)
        active = await _create_model(
            db_session, provider,
            model_id="active-model",
            display_name="Active Model",
            is_active=True,
        )
        disabled = await _create_model(
            db_session, provider,
            model_id="disabled-model",
            display_name="Disabled Model",
            is_active=False,
        )
        await db_session.commit()

        response = await client.get("/api/models/available")
        assert response.status_code == 200
        data = response.json()

        all_models = (
            data.get("image_models", [])
            + data.get("video_models", [])
            + data.get("text_models", [])
        )

        model_ids = [m["id"] for m in all_models]
        assert active.model_id in model_ids, "Active model should be present"
        assert disabled.model_id not in model_ids, "Disabled model must be excluded"

    @pytest.mark.asyncio
    async def test_disabled_model_not_in_list(self, client: AsyncClient, db_session):
        """Only active models appear in /api/models (list all)."""
        provider = await _create_provider(db_session)
        active = await _create_model(
            db_session, provider,
            model_id="active-list",
            is_active=True,
        )
        disabled = await _create_model(
            db_session, provider,
            model_id="disabled-list",
            is_active=False,
        )
        await db_session.commit()

        response = await client.get("/api/models")
        assert response.status_code == 200
        models = response.json()

        model_ids = [m["id"] for m in models]
        assert active.model_id in model_ids
        assert disabled.model_id not in model_ids

    @pytest.mark.asyncio
    async def test_disabled_model_not_in_capability_filter(self, client: AsyncClient, db_session):
        """Disabled models with matching capabilities are still excluded."""
        provider = await _create_provider(db_session)
        await _create_model(
            db_session, provider,
            model_id="active-img2img",
            modality="image",
            capabilities=["image_to_image"],
            is_active=True,
        )
        await _create_model(
            db_session, provider,
            model_id="disabled-img2img",
            modality="image",
            capabilities=["image_to_image"],
            is_active=False,
        )
        await db_session.commit()

        response = await client.get("/api/models/capabilities/image_to_image")
        assert response.status_code == 200
        models = response.json()

        model_ids = [m["id"] for m in models]
        assert "active-img2img" in model_ids
        assert "disabled-img2img" not in model_ids, (
            "Disabled model with matching capability must be excluded"
        )

    @pytest.mark.asyncio
    async def test_disabled_model_not_found_by_id(self, client: AsyncClient, db_session):
        """GET /api/models/{id} returns error for disabled models."""
        provider = await _create_provider(db_session)
        disabled = await _create_model(
            db_session, provider,
            model_id="by-id-disabled",
            is_active=False,
        )
        await db_session.commit()

        response = await client.get(f"/api/models/{disabled.model_id}")
        assert response.status_code == 200
        data = response.json()
        # When not found (or disabled), should return error
        assert "error" in data


# ── Capabilities field ───────────────────────────────────────────────


class TestCapabilitiesField:
    """Verify the capabilities field is present and correct in API responses."""

    @pytest.mark.asyncio
    async def test_capabilities_in_available_response(self, client: AsyncClient, db_session):
        """Each model in /api/models/available includes a capabilities field."""
        provider = await _create_provider(db_session)
        await _create_model(
            db_session, provider,
            model_id="cap-model",
            capabilities=["image_to_image", "text_to_image"],
        )
        await db_session.commit()

        response = await client.get("/api/models/available")
        assert response.status_code == 200
        data = response.json()

        all_models = data["image_models"] + data["video_models"] + data["text_models"]
        cap_model = next((m for m in all_models if m["id"] == "cap-model"), None)
        assert cap_model is not None, "Model should be present"
        assert "capabilities" in cap_model, "Response must include capabilities field"
        assert isinstance(cap_model["capabilities"], dict)
        assert cap_model["capabilities"].get("accepts_text") is True
        assert cap_model["capabilities"].get("outputs_image") is True

    @pytest.mark.asyncio
    async def test_capabilities_defaults_to_empty_list(self, client: AsyncClient, db_session):
        """Models without capabilities return an empty list, not None."""
        provider = await _create_provider(db_session)
        await _create_model(
            db_session, provider,
            model_id="no-cap-model",
            capabilities=None,
        )
        await db_session.commit()

        response = await client.get("/api/models/available")
        assert response.status_code == 200
        data = response.json()

        all_models = data["image_models"] + data["video_models"] + data["text_models"]
        no_cap = next((m for m in all_models if m["id"] == "no-cap-model"), None)
        assert no_cap is not None
        assert isinstance(no_cap["capabilities"], dict)
        assert no_cap["capabilities"].get("accepts_text") is True

    @pytest.mark.asyncio
    async def test_capabilities_in_list_endpoint(self, client: AsyncClient, db_session):
        """/api/models includes capabilities field in each entry."""
        provider = await _create_provider(db_session)
        await _create_model(
            db_session, provider,
            model_id="list-cap-model",
            capabilities=["text_to_image"],
        )
        await db_session.commit()

        response = await client.get("/api/models")
        assert response.status_code == 200
        models = response.json()

        target = next((m for m in models if m["id"] == "list-cap-model"), None)
        assert target is not None
        assert "capabilities" in target
        assert isinstance(target["capabilities"], dict)
        assert target["capabilities"].get("accepts_text") is True
        assert target["capabilities"].get("outputs_image") is True

    @pytest.mark.asyncio
    async def test_capabilities_in_detail_endpoint(self, client: AsyncClient, db_session):
        """/api/models/{id} includes capabilities field."""
        provider = await _create_provider(db_session)
        model = await _create_model(
            db_session, provider,
            model_id="detail-cap-model",
            capabilities=["image_to_video"],
            modality="video",
        )
        await db_session.commit()

        response = await client.get(f"/api/models/{model.model_id}")
        assert response.status_code == 200
        data = response.json()

        assert "capabilities" in data
        assert isinstance(data["capabilities"], dict)
        assert data["capabilities"].get("accepts_text") is True
        assert data["capabilities"].get("outputs_video") is True

    @pytest.mark.asyncio
    async def test_capability_filter_endpoint_returns_only_matching(self, client: AsyncClient, db_session):
        """/api/models/capabilities/{capability} returns only models with that capability."""
        provider = await _create_provider(db_session)
        await _create_model(
            db_session, provider,
            model_id="has-img2img",
            capabilities=["image_to_image"],
        )
        await _create_model(
            db_session, provider,
            model_id="no-img2img",
            capabilities=["text_to_image"],
        )
        await db_session.commit()

        response = await client.get("/api/models/capabilities/image_to_image")
        assert response.status_code == 200
        models = response.json()

        model_ids = [m["id"] for m in models]
        assert "has-img2img" in model_ids
        assert "no-img2img" not in model_ids


# ── Capability query parameter filter ────────────────────────────────


class TestCapabilityQueryParameter:
    """?capability=<name> on /api/models filters by that capability."""

    @pytest.mark.asyncio
    async def test_outputs_image_filter(self, client: AsyncClient, db_session):
        """?capability=outputs_image returns only image models."""
        provider = await _create_provider(db_session)
        img_model = await _create_model(
            db_session, provider,
            model_id="img-model",
            modality="image",
            capabilities=["text_to_image"],
        )
        vid_model = await _create_model(
            db_session, provider,
            model_id="vid-model",
            modality="video",
            capabilities=["text_to_video"],
        )
        await db_session.commit()

        response = await client.get("/api/models?capability=outputs_image")
        assert response.status_code == 200
        models = response.json()

        model_ids = [m["id"] for m in models]
        assert "img-model" in model_ids
        assert "vid-model" not in model_ids
        for m in models:
            caps = m.get("capabilities", {})
            assert isinstance(caps, dict)
            assert caps.get("outputs_image") is True, (
                f"Model {m['id']} should have outputs_image=True"
            )

    @pytest.mark.asyncio
    async def test_outputs_video_filter(self, client: AsyncClient, db_session):
        """?capability=outputs_video returns only video models."""
        provider = await _create_provider(db_session)
        vid_model = await _create_model(
            db_session, provider,
            model_id="vid-model",
            modality="video",
            capabilities=["text_to_video"],
        )
        img_model = await _create_model(
            db_session, provider,
            model_id="img-model",
            modality="image",
            capabilities=["text_to_image"],
        )
        await db_session.commit()

        response = await client.get("/api/models?capability=outputs_video")
        assert response.status_code == 200
        models = response.json()

        model_ids = [m["id"] for m in models]
        assert "vid-model" in model_ids
        assert "img-model" not in model_ids
        for m in models:
            caps = m.get("capabilities", {})
            assert isinstance(caps, dict)
            assert caps.get("outputs_video") is True, (
                f"Model {m['id']} should have outputs_video=True"
            )

    @pytest.mark.asyncio
    async def test_no_capability_returns_all(self, client: AsyncClient, db_session):
        """Without ?capability, all active models are returned."""
        provider = await _create_provider(db_session)
        await _create_model(
            db_session, provider,
            model_id="model-a",
            modality="image",
            capabilities=["text_to_image"],
        )
        await _create_model(
            db_session, provider,
            model_id="model-b",
            modality="video",
            capabilities=["text_to_video"],
        )
        await db_session.commit()

        response = await client.get("/api/models")
        assert response.status_code == 200
        models = response.json()

        model_ids = [m["id"] for m in models]
        assert "model-a" in model_ids
        assert "model-b" in model_ids

    @pytest.mark.asyncio
    async def test_nonexistent_capability_returns_empty(self, client: AsyncClient, db_session):
        """?capability=nonexistent gracefully returns an empty list."""
        provider = await _create_provider(db_session)
        await _create_model(
            db_session, provider,
            model_id="some-model",
            modality="image",
            capabilities=["text_to_image"],
        )
        await db_session.commit()

        response = await client.get("/api/models?capability=accepts_audio")
        assert response.status_code == 200
        models = response.json()
        assert models == []
