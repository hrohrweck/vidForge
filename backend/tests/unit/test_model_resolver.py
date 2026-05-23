import pytest
from app.services.model_resolver import (
    get_family_from_legacy_id,
    resolve_model_variant,
)


class TestGetFamilyFromLegacyId:
    def test_returns_family_for_legacy_variant(self):
        assert get_family_from_legacy_id("wan2.2-t2v") == "wan2.2"
        assert get_family_from_legacy_id("wan2.2-i2v") == "wan2.2"
        assert get_family_from_legacy_id("ltx2.3-t2v") == "ltx2.3"
        assert get_family_from_legacy_id("ltx2.3-fast") == "ltx2.3-fast"

    def test_returns_input_for_family_id(self):
        assert get_family_from_legacy_id("wan2.2") == "wan2.2"
        assert get_family_from_legacy_id("ltx2.3") == "ltx2.3"

    def test_returns_input_for_unknown_id(self):
        assert get_family_from_legacy_id("unknown-model") == "unknown-model"


class TestResolveModelVariant:
    def test_wan_with_seed_image_returns_i2v(self):
        assert resolve_model_variant("wan2.2", has_seed_image=True, is_scene_continuation=False) == "wan2.2_i2v"

    def test_wan_continuation_returns_s2v(self):
        assert resolve_model_variant("wan2.2", has_seed_image=True, is_scene_continuation=True) == "wan2.2_s2v"

    def test_wan_without_seed_returns_t2v(self):
        assert resolve_model_variant("wan2.2", has_seed_image=False, is_scene_continuation=False) == "wan2.2_t2v"

    def test_ltx_fast_always_returns_distilled(self):
        assert resolve_model_variant("ltx2.3-fast", has_seed_image=True, is_scene_continuation=False) == "ltx2.3_distilled"
        assert resolve_model_variant("ltx2.3-fast", has_seed_image=False, is_scene_continuation=False) == "ltx2.3_distilled"

    def test_ltx_with_seed_image_returns_i2v(self):
        assert resolve_model_variant("ltx2.3", has_seed_image=True, is_scene_continuation=False) == "ltx2.3_i2v"

    def test_ltx_without_seed_returns_t2v(self):
        assert resolve_model_variant("ltx2.3", has_seed_image=False, is_scene_continuation=False) == "ltx2.3_t2v"

    def test_raises_for_unknown_family(self):
        with pytest.raises(ValueError, match="Unknown model family"):
            resolve_model_variant("unknown", has_seed_image=False, is_scene_continuation=False)
