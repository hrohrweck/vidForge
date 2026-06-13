"""Tests for PromptEnhancer cleanup of reasoning/thinking output."""

from __future__ import annotations

import pytest

from app.services.llm_service import PromptEnhancer


@pytest.mark.asyncio
async def test_enhance_extracts_prompt_from_thinking_process() -> None:
    raw_response = """Here's a thinking process:

- **Core Idea:** Young man with long hair, sitting alone in a dimly lit room, headphones on, softly singing a poignant, introspective song about feeling lost and questioning life's purpose. The mood is melancholic and vulnerable, with cinematic lighting and shallow depth of field. A subtle, translucent ghost of a vintage television flickers in the background, symbolizing faded memories and unresolved pasts.
   - **Style Request:** Realistic style
   - **Constraints:** Keep core idea, add visual details, keep it concise, no dialogue.

- Subject: Young man, long hair, headphones, singing
   - Setting: Dimly lit room
   - Lighting/Style: Cinematic lighting, shallow depth of field, realistic style
   - Background/Effect: Translucent vintage TV ghost flickering
   - Mood: Melancholic, vulnerable, introspective

- *Lighting:* Warm amber practical light from a desk lamp casting long shadows."""

    enhancer = PromptEnhancer(llm_client=None)
    cleaned = enhancer._clean_enhanced_response(raw_response)

    assert "thinking process" not in cleaned.lower()
    assert "**Core Idea:**" not in cleaned
    assert "- Subject" not in cleaned
    assert "Style Request" not in cleaned
    assert "photorealistic" in cleaned or "cinematic" in cleaned or "young man" in cleaned
    assert "\n" not in cleaned


@pytest.mark.asyncio
async def test_enhance_keeps_simple_prompt() -> None:
    enhancer = PromptEnhancer(llm_client=None)
    cleaned = enhancer._clean_enhanced_response(
        "A young man with long hair sits alone in a dim room, wearing headphones."
    )
    assert cleaned == "A young man with long hair sits alone in a dim room, wearing headphones."
