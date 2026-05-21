"""Script to Video template plugin."""

from .plugin import ScriptToVideoPlugin


def create_plugin() -> ScriptToVideoPlugin:
    return ScriptToVideoPlugin()
