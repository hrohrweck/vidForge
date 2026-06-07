"""Tests for model capability types and normalization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.model_capabilities import (
    GenerationType,
    ModelCapabilities,
    ModelCapability,
    normalize_capabilities,
)


class TestModelCapabilityEnum:
    """ModelCapability enum values match expected strings."""

    def test_values(self):
        assert ModelCapability.TEXT_TO_IMAGE.value == "text_to_image"
        assert ModelCapability.IMAGE_TO_IMAGE.value == "image_to_image"
        assert ModelCapability.IMAGE_EDIT.value == "image_edit"
        assert ModelCapability.TEXT_TO_VIDEO.value == "text_to_video"
        assert ModelCapability.IMAGE_TO_VIDEO.value == "image_to_video"
        assert ModelCapability.FRAME_TO_VIDEO.value == "frame_to_video"
        assert ModelCapability.MULTI_REF_TO_VIDEO.value == "multi_ref_to_video"
        assert ModelCapability.TEXT_TO_TEXT.value == "text_to_text"
        assert ModelCapability.UNKNOWN.value == "unknown"

    def test_membership(self):
        assert len(ModelCapability) == 9


class TestGenerationTypeEnum:
    """GenerationType enum values match expected strings."""

    def test_values(self):
        assert GenerationType.TEXT_TO_IMAGE.value == "text_to_image"
        assert GenerationType.IMAGE_TO_IMAGE.value == "image_to_image"
        assert GenerationType.IMAGE_EDIT.value == "image_edit"
        assert GenerationType.TEXT_TO_VIDEO.value == "text_to_video"
        assert GenerationType.IMAGE_TO_VIDEO.value == "image_to_video"
        assert GenerationType.FRAME_TO_VIDEO.value == "frame_to_video"
        assert GenerationType.MULTI_REF_TO_VIDEO.value == "multi_ref_to_video"
        assert GenerationType.UNKNOWN.value == "unknown"

    def test_membership(self):
        assert len(GenerationType) == 8


class TestModelCapabilitiesModel:
    """ModelCapabilities Pydantic model validation and defaults."""

    def test_defaults(self):
        mc = ModelCapabilities()
        assert mc.accepts_text is False
        assert mc.generation_type == GenerationType.UNKNOWN
        assert mc.capabilities == []

    def test_serialization_roundtrip(self):
        mc = ModelCapabilities(
            accepts_text=True,
            outputs_image=True,
            generation_type=GenerationType.TEXT_TO_IMAGE,
            capabilities=[ModelCapability.TEXT_TO_IMAGE],
        )
        data = mc.model_dump()
        restored = ModelCapabilities.model_validate(data)
        assert restored == mc

    def test_unknown_capability_rejected(self):
        with pytest.raises(ValidationError):
            ModelCapabilities.model_validate({"capabilities": ["bogus"]})

    def test_unknown_generation_type_rejected(self):
        with pytest.raises(ValidationError):
            ModelCapabilities.model_validate({"generation_type": "bogus"})


class TestNormalizeCapabilities:
    """normalize_capabilities infers generation_type + capabilities list."""

    def test_text_to_image(self):
        result = normalize_capabilities(
            {"accepts_text": True, "outputs_image": True}
        )
        assert result.generation_type == GenerationType.TEXT_TO_IMAGE
        assert ModelCapability.TEXT_TO_IMAGE in result.capabilities

    def test_image_to_image_poe_style(self):
        """Poe-style dict: accepts_text + accepts_image + outputs_image."""
        result = normalize_capabilities(
            {
                "accepts_text": True,
                "accepts_image": True,
                "outputs_image": True,
            }
        )
        assert result.generation_type == GenerationType.IMAGE_TO_IMAGE
        assert ModelCapability.TEXT_TO_IMAGE in result.capabilities
        assert ModelCapability.IMAGE_TO_IMAGE in result.capabilities

    def test_text_to_video(self):
        result = normalize_capabilities(
            {"accepts_text": True, "outputs_video": True}
        )
        assert result.generation_type == GenerationType.TEXT_TO_VIDEO
        assert ModelCapability.TEXT_TO_VIDEO in result.capabilities

    def test_image_to_video(self):
        result = normalize_capabilities(
            {
                "accepts_text": True,
                "accepts_image": True,
                "outputs_video": True,
            }
        )
        assert result.generation_type == GenerationType.IMAGE_TO_VIDEO
        assert ModelCapability.IMAGE_TO_VIDEO in result.capabilities
        assert ModelCapability.TEXT_TO_VIDEO in result.capabilities

    def test_image_only_no_outputs_unknown(self):
        """Edge case: accepts_image but no outputs → UNKNOWN."""
        result = normalize_capabilities({"accepts_image": True})
        assert result.generation_type == GenerationType.UNKNOWN
        assert ModelCapability.IMAGE_TO_IMAGE in result.capabilities

    def test_text_model_has_text_capability(self):
        """Text-only model gets TEXT_TO_TEXT in capabilities + UNKNOWN gen."""
        result = normalize_capabilities(
            {"accepts_text": True, "outputs_text": True}
        )
        assert ModelCapability.TEXT_TO_TEXT in result.capabilities
        assert result.generation_type == GenerationType.UNKNOWN

    def test_frame_to_video(self):
        result = normalize_capabilities(
            {
                "accepts_text": True,
                "accepts_start_end_images": True,
                "outputs_video": True,
            }
        )
        assert result.generation_type == GenerationType.FRAME_TO_VIDEO
        assert ModelCapability.FRAME_TO_VIDEO in result.capabilities

    def test_multi_ref_to_video(self):
        result = normalize_capabilities(
            {
                "accepts_text": True,
                "accepts_multiple_images": True,
                "outputs_video": True,
            }
        )
        assert result.generation_type == GenerationType.MULTI_REF_TO_VIDEO
        assert ModelCapability.MULTI_REF_TO_VIDEO in result.capabilities

    def test_empty_dict_returns_unknown(self):
        result = normalize_capabilities({})
        assert result.generation_type == GenerationType.UNKNOWN
        assert ModelCapability.UNKNOWN in result.capabilities

    def test_extra_keys_ignored(self):
        result = normalize_capabilities(
            {
                "accepts_text": True,
                "outputs_image": True,
                "supports_tools": True,
                "supports_web_search": False,
            }
        )
        assert result.generation_type == GenerationType.TEXT_TO_IMAGE
        assert ModelCapability.TEXT_TO_IMAGE in result.capabilities

    def test_passthrough_all_flags(self):
        """All flags pass through to the result object."""
        raw = {
            "accepts_text": True,
            "accepts_image": True,
            "accepts_start_end_images": False,
            "accepts_multiple_images": False,
            "accepts_video": False,
            "outputs_image": True,
            "outputs_video": False,
            "outputs_text": False,
        }
        result = normalize_capabilities(raw)
        assert result.accepts_text is True
        assert result.accepts_image is True
        assert result.outputs_image is True
        assert result.outputs_video is False
        assert result.outputs_text is False


# ────────────────────────────────────────────────────────────────────────────
# build_model_capabilities_context
# ────────────────────────────────────────────────────────────────────────────

from app.services.model_capabilities import (
    build_model_capabilities_context,
    build_reference_capacity_context,
)


def _video_cfg(
    *,
    display_name: str = "wan2.2",
    capabilities: dict | list | None = None,
    max_duration: int | None = None,
    **kwargs,
) -> dict:
    """Factory for a video model-config dict (matching _model_config_to_dict shape)."""
    base: dict = {
        "display_name": display_name,
        "name": "wan2.2",
        "id": "wan2.2",
        "modality": "video",
        "capabilities": capabilities
        if capabilities is not None
        else {"accepts_text": True, "accepts_image": True, "outputs_video": True},
    }
    if max_duration is not None:
        base["max_duration"] = max_duration
    base.update(kwargs)
    return base


def _image_cfg(
    *,
    display_name: str = "flux1-schnell",
    capabilities: dict | list | None = None,
    resolutions: list | None = None,
    max_resolution: str | None = None,
    **kwargs,
) -> dict:
    """Factory for an image model-config dict."""
    base: dict = {
        "display_name": display_name,
        "name": "flux1-schnell",
        "id": "flux1-schnell",
        "modality": "image",
        "capabilities": capabilities
        if capabilities is not None
        else {"accepts_text": True, "outputs_image": True},
    }
    if resolutions is not None:
        base["resolutions"] = resolutions
    if max_resolution is not None:
        base["max_resolution"] = max_resolution
    base.update(kwargs)
    return base


class TestBuildModelCapabilitiesContext:
    """build_model_capabilities_context generates structured prompt text."""

    # ── Generation type instructions ──────────────────────────────────────

    def test_video_image_to_video(self):
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_image": True,
                    "outputs_video": True,
                },
                max_duration=5,
            ),
            image_model_config=None,
        )
        assert "VIDEO MODEL CAPABILITIES:" in result
        assert "Model: wan2.2" in result
        assert "image_to_video" in result
        assert "text prompt + 1 reference image → video" in result
        assert "Max clip duration: 5 seconds" in result
        assert "ONE seed image" in result

    def test_video_text_to_video(self):
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(
                capabilities={"accepts_text": True, "outputs_video": True}
            ),
            image_model_config=None,
        )
        assert "text_to_video" in result
        assert "text prompt only → video" in result
        assert "No reference image is available" in result

    def test_video_frame_to_video(self):
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_start_end_images": True,
                    "outputs_video": True,
                }
            ),
            image_model_config=None,
        )
        assert "frame_to_video" in result
        assert "start image + end image" in result
        assert "start and end frame reference images" in result

    def test_video_multi_ref_to_video(self):
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_multiple_images": True,
                    "outputs_video": True,
                }
            ),
            image_model_config=None,
        )
        assert "multi_ref_to_video" in result
        assert "multiple reference images → video" in result
        assert "multiple reference images to guide" in result

    # ── Image model tests ────────────────────────────────────────────────

    def test_image_text_to_image(self):
        result = build_model_capabilities_context(
            video_model_config=None,
            image_model_config=_image_cfg(
                capabilities={"accepts_text": True, "outputs_image": True}
            ),
        )
        assert "IMAGE MODEL CAPABILITIES:" in result
        assert "Model: flux1-schnell" in result
        assert "text_to_image" in result
        assert "text prompt only — no reference image needed" in result
        assert "No reference image is needed" in result

    def test_image_to_image(self):
        result = build_model_capabilities_context(
            video_model_config=None,
            image_model_config=_image_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_image": True,
                    "outputs_image": True,
                }
            ),
        )
        assert "image_to_image" in result
        assert "text prompt + 1 reference image" in result
        assert "reference image combined" in result

    # ── Constraints ──────────────────────────────────────────────────────

    def test_video_max_duration_from_constraints(self):
        """max_duration pulled from nested constraints dict."""
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(
                constraints={"max_duration": 12},
            ),
            image_model_config=None,
        )
        assert "Max clip duration: 12 seconds" in result

    def test_image_resolutions_flat(self):
        result = build_model_capabilities_context(
            video_model_config=None,
            image_model_config=_image_cfg(
                resolutions=["1024x1024", "512x512"],
                max_resolution="1024x1024",
            ),
        )
        assert "Supported resolutions: 1024x1024, 512x512" in result
        assert "Max resolution: 1024x1024" in result

    def test_image_resolutions_from_constraints(self):
        result = build_model_capabilities_context(
            video_model_config=None,
            image_model_config=_image_cfg(
                constraints={"resolutions": ["640x480", "1280x720"]},
            ),
        )
        assert "Supported resolutions: 640x480, 1280x720" in result

    # ── None / missing inputs ────────────────────────────────────────────

    def test_both_none(self):
        result = build_model_capabilities_context(
            video_model_config=None, image_model_config=None
        )
        assert "No video model selected." in result
        assert "No image model selected." in result

    def test_video_none_image_present(self):
        result = build_model_capabilities_context(
            video_model_config=None,
            image_model_config=_image_cfg(),
        )
        assert "No video model selected." in result
        assert "IMAGE MODEL CAPABILITIES:" in result
        assert "Model: flux1-schnell" in result

    def test_image_none_video_present(self):
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(),
            image_model_config=None,
        )
        assert "VIDEO MODEL CAPABILITIES:" in result
        assert "Model: wan2.2" in result
        assert "No image model selected." in result

    # ── Edge cases ───────────────────────────────────────────────────────

    def test_capabilities_as_list_still_works(self):
        """Capabilities stored as a list → defaults to UNKNOWN."""
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(
                capabilities=["text_to_video"],  # list, not dict
            ),
            image_model_config=None,
        )
        # Should not crash; falls back to UNKNOWN
        assert "VIDEO MODEL CAPABILITIES:" in result
        assert "unknown" in result

    def test_minimal_config_no_extras(self):
        """Minimal config dict without resolutions / max_duration."""
        result = build_model_capabilities_context(
            video_model_config={
                "display_name": "minimal-video",
                "capabilities": {"accepts_text": True, "outputs_video": True},
            },
            image_model_config={
                "display_name": "minimal-image",
                "capabilities": {"accepts_text": True, "outputs_image": True},
            },
        )
        assert "minimal-video" in result
        assert "minimal-image" in result
        # No max_duration / resolutions lines
        assert "Max clip duration" not in result
        assert "Supported resolutions" not in result

    def test_both_models_full_output_ordering(self):
        """Verify the full output structure with both models present."""
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(max_duration=5),
            image_model_config=_image_cfg(
                resolutions=["1024x1024"], max_resolution="1024x1024"
            ),
        )
        lines = result.split("\n")
        # Video section first
        vid_idx = lines.index("VIDEO MODEL CAPABILITIES:")
        img_idx = lines.index("IMAGE MODEL CAPABILITIES:")
        assert vid_idx < img_idx
        # Blank separator between sections
        blank_line = lines[img_idx - 1]
        assert blank_line == ""

    def test_display_name_fallback_to_name(self):
        result = build_model_capabilities_context(
            video_model_config={
                "name": "alt-video",
                "capabilities": {"accepts_text": True, "outputs_video": True},
            },
            image_model_config=None,
        )
        assert "Model: alt-video" in result

    def test_display_name_fallback_to_id(self):
        result = build_model_capabilities_context(
            video_model_config={
                "id": "id-video",
                "capabilities": {"accepts_text": True, "outputs_video": True},
            },
            image_model_config=None,
        )
        assert "Model: id-video" in result

    def test_unknown_generation_type_message(self):
        """Empty capabilities dict → UNKNOWN generation type."""
        result = build_model_capabilities_context(
            video_model_config=_video_cfg(capabilities={}),
            image_model_config=None,
        )
        assert "unknown" in result.lower()


@pytest.mark.reference_capacity
class TestBuildReferenceCapacityContext:
    """build_reference_capacity_context generates reference slot guidance."""

    def test_image_to_video_zero_chars(self):
        """IMAGE_TO_VIDEO with 0 chars → 1 slot available."""
        result = build_reference_capacity_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_image": True,
                    "outputs_video": True,
                }
            ),
            char_count=0,
        )
        assert "accepts up to 1 reference image per scene" in result
        assert "0 slots are consumed by character avatars" in result
        assert "1 slot remains for objects" in result
        assert "The top 1 object will receive reference images" in result

    def test_image_to_video_one_char(self):
        """IMAGE_TO_VIDEO with 1 char → 0 slots available."""
        result = build_reference_capacity_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_image": True,
                    "outputs_video": True,
                }
            ),
            char_count=1,
        )
        assert "accepts up to 1 reference image per scene" in result
        assert "1 slot is consumed by character avatars" in result
        assert "All reference slots consumed by characters" in result
        assert "Objects must be described in words only" in result

    def test_frame_to_video_one_char(self):
        """FRAME_TO_VIDEO with 1 char → 1 slot available."""
        result = build_reference_capacity_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_start_end_images": True,
                    "outputs_video": True,
                }
            ),
            char_count=1,
        )
        assert "accepts up to 2 reference images per scene" in result
        assert "1 slot is consumed by character avatars" in result
        assert "1 slot remains for objects" in result
        assert "The top 1 object will receive reference images" in result

    def test_multi_ref_to_video_two_chars_max_refs_five(self):
        """MULTI_REF_TO_VIDEO with 2 chars and max_refs=5 → 3 available."""
        result = build_reference_capacity_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_multiple_images": True,
                    "outputs_video": True,
                },
                constraints={"max_refs": 5},
            ),
            char_count=2,
        )
        assert "accepts up to 5 reference images per scene" in result
        assert "2 slots are consumed by character avatars" in result
        assert "3 slots remain for objects" in result
        assert "The top 3 objects will receive reference images" in result

    def test_text_to_video_zero_available(self):
        """TEXT_TO_VIDEO → 0 slots, text-only model."""
        result = build_reference_capacity_context(
            video_model_config=_video_cfg(
                capabilities={"accepts_text": True, "outputs_video": True}
            ),
            char_count=0,
        )
        assert "does not accept reference images" in result
        assert "All objects must be described in words only" in result

    def test_none_model_returns_unknown(self):
        """No video model → unknown capacity."""
        result = build_reference_capacity_context(
            video_model_config=None,
            char_count=0,
        )
        assert "Reference capacity: unknown (no video model selected)" == result

    def test_more_chars_than_slots_warning(self):
        """More characters than slots → warning message."""
        result = build_reference_capacity_context(
            video_model_config=_video_cfg(
                capabilities={
                    "accepts_text": True,
                    "accepts_image": True,
                    "outputs_video": True,
                }
            ),
            char_count=3,
        )
        assert "WARNING: More characters than reference slots" in result
        assert "Only 1 total slot available" in result
