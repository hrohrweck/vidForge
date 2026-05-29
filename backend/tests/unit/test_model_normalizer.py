import pytest

from app.services.model_normalizer import normalize_provider_model


# ---------------------------------------------------------------------------
# AtlasCloud tests
# ---------------------------------------------------------------------------


class TestAtlasCloudNormalization:
    def test_image_type_maps_to_image_modality_and_generate_endpoint(self):
        result = normalize_provider_model("atlascloud", {
            "model": "flux-schnell",
            "type": "Image",
            "displayName": "Flux Schnell",
        })
        assert result["modality"] == "image"
        assert result["endpoint_type"] == "generateImage"
        assert result["model_id"] == "flux-schnell"
        assert result["provider_model_id"] == "flux-schnell"
        assert result["display_name"] == "Flux Schnell"
        assert not result["capabilities"]["supports_chat"]

    def test_video_type_maps_to_video_modality_and_generate_endpoint(self):
        result = normalize_provider_model("atlascloud", {
            "model": "wan-2.2",
            "type": "Video",
            "displayName": "Wan 2.2",
        })
        assert result["modality"] == "video"
        assert result["endpoint_type"] == "generateVideo"
        assert not result["capabilities"]["supports_chat"]

    def test_text_type_maps_to_text_modality_and_chat_endpoint(self):
        result = normalize_provider_model("atlascloud", {
            "model": "llama-3.3",
            "type": "Text",
            "displayName": "Llama 3.3",
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert result["capabilities"]["supports_chat"] is True


# ---------------------------------------------------------------------------
# Poe tests
# ---------------------------------------------------------------------------


class TestPoeNormalization:
    def test_image_output_modality_maps_to_generate_image_endpoint(self):
        result = normalize_provider_model("poe", {
            "id": "flux-schnell",
            "root": "flux-schnell-v1",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["image"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {"display_name": "Flux Schnell"},
        })
        assert result["modality"] == "image"
        assert result["endpoint_type"] == "generateImage"
        assert result["model_id"] == "flux-schnell"
        assert result["provider_model_id"] == "flux-schnell-v1"
        assert result["display_name"] == "Flux Schnell"
        caps = result["capabilities"]
        assert caps["outputs_image"] is True
        assert caps["outputs_text"] is False
        assert caps["outputs_video"] is False

    def test_text_output_modality_maps_to_chat_endpoint_with_features(self):
        result = normalize_provider_model("poe", {
            "id": "glm-5.1",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "supported_features": ["tools", "web_search"],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        caps = result["capabilities"]
        assert caps["outputs_text"] is True
        assert caps["accepts_text"] is True
        assert caps["supports_tools"] is True
        assert caps["supports_web_search"] is True

    def test_multimodal_output_prioritizes_video_over_image_over_text(self):
        result = normalize_provider_model("poe", {
            "id": "multimodal-bot",
            "architecture": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text", "image", "video"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["modality"] == "video"
        assert result["endpoint_type"] == "generateVideo"
        caps = result["capabilities"]
        assert caps["outputs_text"] is True
        assert caps["outputs_image"] is True
        assert caps["outputs_video"] is True
        assert caps["accepts_text"] is True
        assert caps["accepts_image"] is True

    def test_image_prioritized_over_text_for_modality(self):
        result = normalize_provider_model("poe", {
            "id": "image-chat",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text", "image"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["modality"] == "image"
        assert result["endpoint_type"] == "generateImage"

    def test_v1_images_endpoint_forces_generate_image(self):
        result = normalize_provider_model("poe", {
            "id": "img-api-bot",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["image", "text"],
            },
            "supported_features": [],
            "supported_endpoints": ["/v1/images", "/v1/chat/completions"],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["endpoint_type"] == "generateImage"


# ---------------------------------------------------------------------------
# Error / edge case tests
# ---------------------------------------------------------------------------


class TestNormalizationErrors:
    def test_unknown_provider_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider type"):
            normalize_provider_model("openai", {"model": "gpt-4"})

    def test_atlascloud_without_type_defaults_to_text(self):
        result = normalize_provider_model("atlascloud", {
            "model": "some-model",
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert result["capabilities"]["supports_chat"] is True

    def test_atlascloud_minimal_data_does_not_crash(self):
        result = normalize_provider_model("atlascloud", {
            "model": "bare-minimum",
        })
        assert result["model_id"] == "bare-minimum"
        assert result["display_name"] == "bare-minimum"
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert result["cost_config"] == {"currency": "credits"}

    def test_poe_minimal_data_does_not_crash(self):
        result = normalize_provider_model("poe", {
            "id": "minimal-bot",
            "architecture": {},
            "supported_features": [],
            "supported_endpoints": [],
            "pricing": {},
            "context_window": {},
            "metadata": {},
        })
        assert result["model_id"] == "minimal-bot"
        assert result["provider_model_id"] == "minimal-bot"
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        caps = result["capabilities"]
        assert caps["outputs_text"] is False
        assert caps["outputs_image"] is False
        assert caps["outputs_video"] is False
        assert caps["supports_tools"] is False

    def test_poe_missing_optional_fields_does_not_crash(self):
        result = normalize_provider_model("poe", {
            "id": "no-extras",
            "architecture": {
                "input_modalities": [],
                "output_modalities": ["text"],
            },
            "supported_features": [],
            "supported_endpoints": [],
            "metadata": {},
        })
        assert result["modality"] == "text"
        assert result["endpoint_type"] == "chat_completions"
        assert "cost_config" not in result
        assert "constraints" not in result
