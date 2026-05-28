"""TDD verification: hardcoded model checks removed from provider code.

These tests do NOT import provider modules — they grep the raw source files
to verify that the refactoring has been properly applied.

Rule: zero hardcoded model-name checks / model-set constants must remain.
Payload construction should use ModelConfigService instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# -- Absolute paths to the source files under test ---------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

ATLASCLOUD_PY = PROJECT_ROOT / "app" / "services" / "providers" / "atlascloud.py"
POE_PY = PROJECT_ROOT / "app" / "services" / "providers" / "poe.py"
MEDIA_GENERATOR_PY = PROJECT_ROOT / "app" / "services" / "media_generator.py"


def _read(path: Path) -> str:
    """Read a source file, skipping lines that are only comments."""
    return path.read_text()


# ============================================================================
# AtlasCloud — hardcoded model checks must be GONE
# ============================================================================


class TestAtlasCloudNoHardcodedModelChecks:
    """Verify atlascloud.py has no hardcoded model-name branching."""

    def test_no_hardcoded_model_checks_in_atlascloud(self):
        """`any(m in model.lower() for m in …)` pattern must not exist."""
        content = _read(ATLASCLOUD_PY)
        assert "any(m in model.lower()" not in content, (
            "atlascloud.py still contains `any(m in model.lower()` "
            "— a hardcoded model-name check pattern"
        )

    def test_no_is_veo_lite_flag(self):
        """`is_veo_lite` sentinel must not exist."""
        content = _read(ATLASCLOUD_PY)
        assert "is_veo_lite" not in content, (
            "atlascloud.py still contains `is_veo_lite` flag"
        )

    def test_imports_model_config_service(self):
        """Must import ModelConfigService for payload construction."""
        content = _read(ATLASCLOUD_PY)
        assert "ModelConfigService" in content, (
            "atlascloud.py does not import ModelConfigService"
        )


# ============================================================================
# Poe — hardcoded model-set constants must be GONE
# ============================================================================


class TestPoeNoHardcodedModelSets:
    """Verify poe.py has no hardcoded model-set constants."""

    def test_no_video_api_models_set(self):
        """`_VIDEO_API_MODELS` set must not exist."""
        content = _read(POE_PY)
        assert "_VIDEO_API_MODELS" not in content, (
            "poe.py still defines `_VIDEO_API_MODELS` set"
        )

    def test_no_is_video_api_model_method(self):
        """`_is_video_api_model` method/function must not exist."""
        content = _read(POE_PY)
        assert "_is_video_api_model" not in content, (
            "poe.py still defines `_is_video_api_model`"
        )

    def test_no_tool_capable_models_set(self):
        """`_TOOL_CAPABLE_TEXT_MODELS` set must not exist."""
        content = _read(POE_PY)
        assert "_TOOL_CAPABLE_TEXT_MODELS" not in content, (
            "poe.py still defines `_TOOL_CAPABLE_TEXT_MODELS` set"
        )

    def test_no_poe_text_models_set(self):
        """`_POE_TEXT_MODELS` set must not exist."""
        content = _read(POE_PY)
        assert "_POE_TEXT_MODELS" not in content, (
            "poe.py still defines `_POE_TEXT_MODELS` set"
        )

    def test_imports_model_config_service(self):
        """Must import ModelConfigService for payload construction."""
        content = _read(POE_PY)
        assert "ModelConfigService" in content, (
            "poe.py does not import ModelConfigService"
        )


# ============================================================================
# Media Generator — hardcoded workflow maps must be GONE
# ============================================================================


class TestMediaGeneratorNoHardcodedWorkflowMap:
    """Verify media_generator.py has no hardcoded workflow map."""

    def test_no_video_workflow_map(self):
        """`VIDEO_WORKFLOW_MAP` constant must not exist."""
        content = _read(MEDIA_GENERATOR_PY)
        assert "VIDEO_WORKFLOW_MAP" not in content, (
            "media_generator.py still defines `VIDEO_WORKFLOW_MAP`"
        )


# ============================================================================
# Positive checks — ModelConfigService IS used
# ============================================================================


class TestModelConfigServiceIntegration:
    """Verify payload construction uses ModelConfigService."""

    def test_atlascloud_uses_model_config_service(self):
        """AtlasCloud must reference model_config_service for model queries."""
        content = _read(ATLASCLOUD_PY)
        assert "model_config_service" in content.lower(), (
            "atlascloud.py does not reference model_config_service"
        )

    def test_poe_uses_model_config_service(self):
        """Poe must reference model_config_service for model queries."""
        content = _read(POE_PY)
        assert "model_config_service" in content.lower(), (
            "poe.py does not reference model_config_service"
        )
