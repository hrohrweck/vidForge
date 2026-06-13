"""Tests for the prompt_to_video scene planner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.llm_service import LLMClient
from plugins.prompt_to_video.planner import (
    _ensure_concise_prompts,
    _ensure_style_prefix,
    _extract_json_with_scenes,
    _fallback_scenes,
    _parse_response,
    _style_prefix,
)


def test_extract_json_with_scenes_finds_json_in_thinking_text() -> None:
    response = """
Okay, let me think about this visually.

- Opening: establish the room
- Development: show emotion

{"scenes": [{"start_time": 0.0, "end_time": 5.0, "visual_description": "A young man sits alone.", "image_prompt": "cinematic style: a young man with long hair sitting alone, photorealistic", "mood": "melancholic", "camera_movement": "static", "seed_image_prompt": "photorealistic young man"}]}

Hope that helps!
"""
    parsed = _extract_json_with_scenes(response)
    assert parsed is not None
    assert "scenes" in parsed
    assert len(parsed["scenes"]) == 1


def test_extract_json_with_scenes_ignores_unrelated_braces() -> None:
    response = 'Some text with {"foo": "bar"} and {"scenes": [{"start_time":0,"end_time":5,"visual_description":"x","image_prompt":"y","mood":"neutral","camera_movement":"static"}]}'
    parsed = _extract_json_with_scenes(response)
    assert parsed is not None
    assert len(parsed["scenes"]) == 1


def test_parse_response_valid_json() -> None:
    response = """{"scenes": [{"start_time": 0.0, "end_time": 5.0, "visual_description": "A young man sits alone.", "image_prompt": "cinematic style: a young man with long hair sitting alone, photorealistic", "mood": "melancholic", "camera_movement": "static"}]}"""
    result = _parse_response(response, 30, original_prompt="A young man...", style="realistic")
    assert not result.get("_is_fallback")
    assert len(result["scenes"]) == 1


def test_parse_response_fallback_distributes_sentences() -> None:
    prompt = (
        "A young man with long hair sits alone in a dim room. "
        "He puts on headphones and closes his eyes. "
        "A ghostly television flickers behind him. "
        "Warm light from a desk lamp casts long shadows."
    )
    result = _parse_response(
        "not valid json at all",
        target_duration=30,
        original_prompt=prompt,
        style="realistic",
    )
    assert result.get("_is_fallback")
    scenes = result["scenes"]
    assert len(scenes) == 6
    prompts = [s["image_prompt"] for s in scenes]
    # Each scene should receive a slice of the prompt, not the same text repeated.
    assert len(set(prompts)) > 1
    # Prompts should not be truncated with "..."
    assert all("..." not in p for p in prompts)
    # All prompts should start with the realistic style prefix.
    prefix = _style_prefix("realistic")
    assert all(p.startswith(prefix) for p in prompts)


def test_fallback_scenes_even_split() -> None:
    prompt = "First scene happens. Second scene happens. Third scene happens."
    scenes = _fallback_scenes(30, prompt, style="anime")
    assert len(scenes) == 6
    prefix = _style_prefix("anime")
    assert scenes[0]["image_prompt"].startswith(prefix)
    assert "..." not in scenes[0]["image_prompt"]


def test_ensure_style_prefix_adds_missing_prefix() -> None:
    scenes = [{"image_prompt": "a cat in a hat"}]
    _ensure_style_prefix(scenes, "realistic")
    assert scenes[0]["image_prompt"].startswith(_style_prefix("realistic"))


def test_ensure_style_prefix_keeps_existing_prefix() -> None:
    scenes = [{"image_prompt": "anime style: a cat in a hat"}]
    _ensure_style_prefix(scenes, "anime")
    assert scenes[0]["image_prompt"] == "anime style: a cat in a hat"


@pytest.mark.asyncio
async def test_ensure_concise_prompts_shortens_long_prompts() -> None:
    long_prompt = (
        "cinematic style: a very long and overly detailed description of a "
        "young man with long hair sitting alone in a dimly lit room wearing "
        "headphones and softly singing while a translucent vintage television "
        "flickers in the background casting warm amber light across the walls"
    )
    scenes = [
        {"image_prompt": long_prompt},
        {"image_prompt": "cinematic style: short prompt"},
    ]

    with patch.object(LLMClient, "generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = (
            "cinematic style: a young man sings alone in a dim room with a ghostly TV"
        )
        llm = LLMClient()
        await _ensure_concise_prompts(scenes, "realistic", llm)

    assert mock_generate.await_count == 1
    assert scenes[0]["image_prompt"] == (
        "cinematic style: a young man sings alone in a dim room with a ghostly TV"
    )
    assert scenes[1]["image_prompt"] == "cinematic style: short prompt"


@pytest.mark.asyncio
async def test_ensure_concise_prompts_adds_prefix_when_missing() -> None:
    scenes = [{"image_prompt": "a" * 500}]

    with patch.object(LLMClient, "generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "a young man sits alone"
        llm = LLMClient()
        await _ensure_concise_prompts(scenes, "realistic", llm)

    assert scenes[0]["image_prompt"].startswith(_style_prefix("realistic"))
