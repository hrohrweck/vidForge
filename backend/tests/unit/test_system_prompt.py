"""Tests for SYSTEM_PROMPT content and constraints."""

import pytest

from app.chatbot.service import SYSTEM_PROMPT


class TestSystemPrompt:
    """Verify SYSTEM_PROMPT meets content and length requirements."""

    def test_length_within_limit(self):
        """SYSTEM_PROMPT must be <= 1500 characters."""
        assert len(SYSTEM_PROMPT) <= 1500, f"Prompt is {len(SYSTEM_PROMPT)} chars, limit 1500"

    def test_tool_families_mentioned(self):
        """All required tool families must be present in SYSTEM_PROMPT."""
        required = ["jobs", "scenes", "media", "projects", "styles", "avatars"]
        for term in required:
            assert term in SYSTEM_PROMPT, f"Missing tool family: {term}"