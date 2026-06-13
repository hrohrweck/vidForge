"""Tests for job input validation and serialization."""

from __future__ import annotations

import pytest

from app.api.jobs import _validate_job_input
from plugins.prompt_to_video.schemas import PromptToVideoInput


class FakePlugin:
    """Minimal plugin stand-in that exposes the prompt_to_video input schema."""

    def get_input_schema(self) -> type:
        return PromptToVideoInput


class FakeTemplate:
    """Minimal template stand-in for validation tests."""

    def __init__(self, plugin_id: str) -> None:
        self.config = {"plugin_id": plugin_id}


@pytest.fixture
def patched_get_plugin(monkeypatch):
    monkeypatch.setattr("app.api.jobs.get_plugin", lambda plugin_id: FakePlugin())


def test_validate_job_input_serializes_avatar_uuids_as_strings(patched_get_plugin) -> None:
    """UUIDs in avatar assignments must be dumped as strings for JSONB storage."""
    avatar_id = "05d5f74b-f051-4ed3-b9a0-79bb299cbad6"
    template = FakeTemplate("prompt_to_video")

    validated = _validate_job_input(
        template,
        {
            "prompt": "robot in a neon city",
            "duration": 15,
            "avatars": [{"avatar_id": avatar_id}],
        },
    )

    assert validated["duration"] == 15
    assert validated["avatars"][0]["avatar_id"] == avatar_id
    # The stored value must be JSON-serializable (plain strings, not UUID objects).
    assert isinstance(validated["avatars"][0]["avatar_id"], str)


def test_validate_job_input_rejects_unknown_extra_fields(patched_get_plugin) -> None:
    """The plugin schema forbids fields it does not recognize."""
    template = FakeTemplate("prompt_to_video")

    with pytest.raises(Exception):  # HTTPException raised internally
        _validate_job_input(
            template,
            {"prompt": "test", "reference_image_url": "http://example.com/img.png"},
        )
