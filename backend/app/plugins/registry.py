"""
Plugin registry — discovers, loads, and provides access to template plugins.

Bundled plugins live in ``backend/plugins/`` (top-level, next to ``app/``).
Each plugin package must export a ``create_plugin()`` function that returns
a :class:`~app.plugins.base.PluginBase` instance.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins.base import PluginBase

logger = logging.getLogger(__name__)

_PLUGINS: dict[str, PluginBase] = {}

# Directory that holds bundled plugin packages.
_BUILTIN_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"


def discover_plugins(plugin_dirs: list[Path] | None = None) -> None:
    """Scan plugin directories and register all found plugins."""
    global _PLUGINS

    # Ensure the backend root (parent of app/ and plugins/) is on sys.path
    # so that ``import plugins.xxx`` works in Celery workers.
    import sys
    backend_root = str(_BUILTIN_DIR.resolve().parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    dirs = plugin_dirs or [_BUILTIN_DIR]
    for d in dirs:
        if not d.is_dir():
            continue
        for pkg in sorted(d.iterdir()):
            if not (pkg / "__init__.py").exists():
                continue
            if pkg.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"plugins.{pkg.name}")
                factory = getattr(mod, "create_plugin", None)
                if factory is None:
                    logger.warning("Plugin %s has no create_plugin()", pkg.name)
                    continue
                plugin = factory()
                if plugin.plugin_id in _PLUGINS:
                    existing = _PLUGINS[plugin.plugin_id]
                    raise ValueError(
                        f"Duplicate plugin_id '{plugin.plugin_id}' from {pkg.name}; "
                        f"already registered by {existing.__class__.__module__}"
                    )
                _PLUGINS[plugin.plugin_id] = plugin
                logger.info("[Plugin] Registered %s (%s)", plugin.plugin_id, plugin.display_name)
            except Exception:
                logger.exception("Failed to load plugin %s", pkg.name)


def get_plugin(plugin_id: str) -> PluginBase | None:
    """Return a registered plugin by its ID, or ``None``."""
    return _PLUGINS.get(plugin_id)


def get_all_plugins() -> dict[str, PluginBase]:
    """Return a copy of the plugin registry."""
    return dict(_PLUGINS)


def get_plugin_for_template(template_config: dict) -> PluginBase | None:
    """Find the plugin that handles a given template config.

    Looks up ``config["plugin_id"]`` first, then falls back to matching
    ``config["workflow_type"]`` to a plugin_id.
    """
    # Explicit plugin_id
    pid = template_config.get("plugin_id")
    if pid:
        return get_plugin(pid)

    # Legacy: map workflow_type to plugin_id
    wf = template_config.get("workflow_type", "")
    mapping = {
        "scene_based": "music_video",
        "standard": "prompt_to_video",
    }
    pid = mapping.get(wf)
    if pid:
        return get_plugin(pid)

    # Final fallback: try to match template name
    name = template_config.get("name", template_config.get("template_file", ""))
    name_lower = name.lower()
    for plugin in _PLUGINS.values():
        if plugin.plugin_id in name_lower:
            return plugin

    return None
