"""Music Video (Scene-Based) template plugin."""

from .plugin import MusicVideoPlugin


def create_plugin() -> MusicVideoPlugin:
    return MusicVideoPlugin()
