"""Tests for SYSTEM_PROMPT content and constraints."""

from app.chatbot.service import SYSTEM_PROMPT_TEMPLATE


class TestSystemPrompt:
    """Verify SYSTEM_PROMPT meets content and length requirements."""

    def test_length_within_limit(self):
        """Formatted SYSTEM_PROMPT must be <= 1500 characters."""
        prompt = SYSTEM_PROMPT_TEMPLATE.format(autonomy_mode="confirm")
        assert len(prompt) <= 1500, f"Prompt is {len(prompt)} chars, limit 1500"

    def test_tool_families_mentioned(self):
        """All required tool families must be present in SYSTEM_PROMPT."""
        prompt = SYSTEM_PROMPT_TEMPLATE.format(autonomy_mode="confirm")
        required = ["jobs", "scenes", "media", "projects", "styles", "avatars"]
        for term in required:
            assert term in prompt, f"Missing tool family: {term}"
