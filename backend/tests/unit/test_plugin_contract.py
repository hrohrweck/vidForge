"""Characterization tests for the plugin base public contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.plugins.base import PluginBase
from app.plugins.registry import discover_plugins, get_plugin
from app.workers.dispatcher import _validate_plan_scenes_result


class MinimalPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "minimal"

    @property
    def display_name(self) -> str:
        return "Minimal"

    @property
    def description(self) -> str:
        return "Minimal plugin"

    def get_template_definition(self) -> dict:
        return {"inputs": [], "pipeline": []}

    async def plan_scenes(self, db, job, context):
        return {"scene_count": 0}


def test_plugin_base_public_defaults_survive_split():
    plugin = MinimalPlugin()

    assert plugin.plugin_id == "minimal"
    assert plugin.get_ui_schema() == {}
    assert plugin.get_editor_panels() == [
        {"id": "scenes", "label": "Scenes", "component": "SceneGrid"},
        {"id": "timeline", "label": "Timeline", "component": "Timeline"},
        {"id": "export", "label": "Export", "component": "ExportPanel"},
    ]
    assert plugin.get_export_options_schema() == {}

    # Methods moved to mixins remain available on PluginBase instances.
    for name in (
        "enrich_inputs",
        "generate_images",
        "generate_videos",
        "render",
        "rerender_scene_image",
        "rerender_scene_video",
    ):
        assert callable(getattr(plugin, name))


def test_plan_scenes_result_validation_accepts_minimal_dict():
    assert _validate_plan_scenes_result({"scene_count": 0}) == {"scene_count": 0}
    assert _validate_plan_scenes_result({"summary": "ok"}) == {"summary": "ok"}


@pytest.mark.parametrize("result", [None, [], "bad"])
def test_plan_scenes_result_validation_rejects_non_dict(result):
    with pytest.raises(ValueError, match="must return a dict"):
        _validate_plan_scenes_result(result)


@pytest.mark.parametrize("scene_count", [-1, 1.2, "1", True])
def test_plan_scenes_result_validation_rejects_bad_scene_count(scene_count):
    with pytest.raises(ValueError, match="scene_count"):
        _validate_plan_scenes_result({"scene_count": scene_count})


def test_discover_plugins_rejects_duplicate_plugin_id(tmp_path, monkeypatch):
    backend_root = tmp_path / "backend_root"
    plugin_root = backend_root / "plugins"
    plugin_root.mkdir(parents=True)

    for package in ("first", "second"):
        pkg = plugin_root / package
        pkg.mkdir()
        (pkg / "__init__.py").write_text(
            "from app.plugins.base import PluginBase\n"
            "class DemoPlugin(PluginBase):\n"
            "    @property\n"
            "    def plugin_id(self): return 'duplicate'\n"
            "    @property\n"
            f"    def display_name(self): return '{package}'\n"
            "    @property\n"
            "    def description(self): return 'demo'\n"
            "    def get_template_definition(self): return {}\n"
            "    async def plan_scenes(self, db, job, context): return {'scene_count': 0}\n"
            "def create_plugin(): return DemoPlugin()\n"
        )

    monkeypatch.syspath_prepend(str(backend_root))
    for mod_name in ("plugins.first", "plugins.second"):
        sys.modules.pop(mod_name, None)

    discover_plugins([plugin_root])

    assert get_plugin("duplicate") is not None
