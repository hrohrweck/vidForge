"""TDD import migration verification tests.

Verifies that all critical imports work after legacy file deletion
and that removed files no longer exist on disk.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SERVICES_DIR = PROJECT_ROOT / "app" / "services"


# ============================================================================
# Test 1: app.api.models router import
# ============================================================================


def test_models_api_router_imports() -> None:
    """`from app.api.models import router` must succeed."""
    from app.api.models import router  # noqa: PLC0415

    assert router is not None
    assert getattr(router, "routes", None) is not None, (
        "Expected router to have routes attribute (APIRouter)"
    )


# ============================================================================
# Test 2: app.chatbot.tools import
# ============================================================================


def test_chatbot_tools_imports() -> None:
    """`from app.chatbot.tools import ...` must work for key symbols."""
    from app.chatbot.tools import (  # noqa: PLC0415
        ToolContext,
        ToolDefinition,
        ToolRegistry,
        create_builtin_registry,
    )

    assert ToolRegistry is not None
    assert ToolContext is not None
    assert ToolDefinition is not None
    assert callable(create_builtin_registry)


# ============================================================================
# Test 3: app.services.media_generator import
# ============================================================================


def test_media_generator_imports() -> None:
    """`from app.services.media_generator import generate_image` must work."""
    from app.services.media_generator import generate_image  # noqa: PLC0415

    assert callable(generate_image)


# ============================================================================
# Test 4: model_config.py DELETED
# ============================================================================


def test_model_config_file_deleted() -> None:
    """`backend/app/services/model_config.py` must NOT exist on disk."""
    path = SERVICES_DIR / "model_config.py"
    assert not path.exists(), (
        f"Legacy file {path} should have been deleted during import migration"
    )


# ============================================================================
# Test 5: model_registry.py DELETED
# ============================================================================


def test_model_registry_file_deleted() -> None:
    """`backend/app/services/model_registry.py` must NOT exist on disk."""
    path = SERVICES_DIR / "model_registry.py"
    assert not path.exists(), (
        f"Legacy file {path} should have been deleted during import migration"
    )


# ============================================================================
# Test 6: model_config_service import
# ============================================================================


def test_model_config_service_imports() -> None:
    """`from app.services.model_config_service import ModelConfigService` must work."""
    from app.services.model_config_service import ModelConfigService  # noqa: PLC0415

    assert ModelConfigService is not None


# ============================================================================
# Test 7: all provider imports work without errors
# ============================================================================


def test_no_import_errors_in_providers() -> None:
    """All provider classes importable without ImportError."""
    from app.services.providers.atlascloud import AtlasCloudProvider  # noqa: PLC0415
    from app.services.providers.base import ComfyUIProvider  # noqa: PLC0415
    from app.services.providers.comfyui_direct import ComfyUIDirectProvider  # noqa: PLC0415
    from app.services.providers.poe import PoeProvider  # noqa: PLC0415

    assert AtlasCloudProvider is not None
    assert ComfyUIProvider is not None
    assert ComfyUIDirectProvider is not None
    assert PoeProvider is not None


# ============================================================================
# Bonus: importlib-based smoke test — verifies modules are importable
# even when the fixture loader might have side-effects.
# ============================================================================


@pytest.mark.parametrize(
    "module_name, attr_name",
    [
        ("app.api.models", "router"),
        ("app.chatbot.tools", "ToolRegistry"),
        ("app.services.media_generator", "generate_image"),
        ("app.services.model_config_service", "ModelConfigService"),
        ("app.services.providers.atlascloud", "AtlasCloudProvider"),
        ("app.services.providers.poe", "PoeProvider"),
        ("app.services.providers.comfyui_direct", "ComfyUIDirectProvider"),
    ],
)
def test_importlib_imports_succeed(module_name: str, attr_name: str) -> None:
    """Each critical module/attribute pair is importable via importlib."""
    mod = importlib.import_module(module_name)
    assert hasattr(mod, attr_name), (
        f"Module {module_name} should have attribute {attr_name}"
    )
