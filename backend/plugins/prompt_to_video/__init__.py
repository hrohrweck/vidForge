"""Prompt to Video template plugin."""

from .plugin import PromptToVideoPlugin


def create_plugin() -> PromptToVideoPlugin:
    return PromptToVideoPlugin()
