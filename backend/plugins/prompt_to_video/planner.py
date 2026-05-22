"""
Scene planner for the Prompt-to-Video template.

Uses the LLM to break a single prompt into a series of 3–6 second
visual segments, each with its own image prompt.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm_service import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a video director. Break the user's prompt into a series of short visual scenes for AI video generation.

Each scene should be 3-15 seconds long. Output ONLY valid JSON:
{"scenes": [{"start_time": 0.0, "end_time": 5.0, "visual_description": "description", "image_prompt": "detailed image prompt", "mood": "mood", "camera_movement": "movement"}]}

Guidelines:
- Scene duration: 3-15 seconds each — longer scenes allow for richer visual storytelling
- Image prompts: 10-25 words, highly visual, specific
- CRITICAL: Every image_prompt MUST begin with the requested visual style (e.g. "anime style: ...", "cinematic style: ...", "photorealistic: ..."). This ensures visual consistency across all scenes.
- Ensure smooth narrative flow between scenes
- Match mood to the content
- Camera movements: static, pan_left, pan_right, zoom_in, zoom_out, tilt_up, orbit
- Total duration should match the requested duration"""


async def plan_scenes_from_prompt(
    prompt: str,
    duration: float = 10,
    style: str = "realistic",
) -> list[dict[str, Any]]:
    """Plan scenes from a single text prompt.

    Returns a list of scene dicts with keys:
    ``start_time``, ``end_time``, ``visual_description``,
    ``image_prompt``, ``mood``, ``camera_movement``.
    """
    llm = LLMClient()
    try:
        user_prompt = (
            f"Create a scene plan for a {duration}-second video.\n"
            f"Style: {style}\n\n"
            f"Prompt: {prompt}"
        )
        response = await llm.generate(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.7,
        )
        return _parse_response(response, duration)
    finally:
        await llm.close()


def _parse_response(response: str, target_duration: float) -> list[dict[str, Any]]:
    """Parse LLM response into a list of scene dicts."""
    response = response.strip()

    # Strip code fences
    if response.startswith("```"):
        parts = response.split("```")
        for part in parts:
            if "scenes" in part:
                response = part.replace("json", "", 1).strip()
                break

    parsed: dict | None = None

    # Try direct JSON parse
    for candidate in [response, response.replace("```json", "").replace("```", "")]:
        candidate = candidate.strip()
        if candidate.startswith("{") and "scenes" in candidate:
            try:
                parsed = json.loads(candidate)
                break
            except json.JSONDecodeError:
                pass

    # Try regex extraction
    if not parsed:
        m = re.search(r'\{.*?"scenes".*?\}', response, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    # Try brace-matching (handles truncated JSON)
    if not parsed:
        parsed = _extract_by_brace_matching(response)

    if not parsed or "scenes" not in parsed:
        logger.warning("LLM response could not be parsed, falling back to single scene")
        return _fallback_scenes(target_duration)

    scenes = parsed["scenes"]
    if not scenes:
        return _fallback_scenes(target_duration)

    # Validate and fix timing
    return _fix_scene_timing(scenes, target_duration)


def _extract_by_brace_matching(text: str) -> dict | None:
    start = text.find("{")
    if start == -1:
        return None
    for end in range(start + 1, len(text) + 1):
        try:
            parsed = json.loads(text[start:end])
            if "scenes" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _fallback_scenes(duration: float) -> list[dict[str, Any]]:
    """Create simple evenly-spaced scenes as a fallback."""
    clip_duration = min(5.0, duration)
    num_scenes = max(1, int(duration / clip_duration))
    actual_duration = duration / num_scenes

    return [
        {
            "start_time": round(i * actual_duration, 2),
            "end_time": round((i + 1) * actual_duration, 2),
            "visual_description": f"Scene {i + 1}",
            "image_prompt": f"Visual representation of scene {i + 1}",
            "mood": "neutral",
            "camera_movement": "static",
        }
        for i in range(num_scenes)
    ]


def _fix_scene_timing(
    scenes: list[dict], duration: float,
) -> list[dict[str, Any]]:
    """Ensure scenes cover the full duration without gaps."""
    scenes.sort(key=lambda s: s.get("start_time", 0))

    fixed: list[dict[str, Any]] = []
    expected_start = 0.0

    for i, scene in enumerate(scenes):
        scene["start_time"] = max(scene.get("start_time", expected_start), expected_start)

        if i == len(scenes) - 1:
            scene["end_time"] = duration
        else:
            next_start = scenes[i + 1].get("start_time", duration)
            scene["end_time"] = min(scene.get("end_time", next_start), next_start)

        if scene["end_time"] <= scene["start_time"]:
            scene["end_time"] = scene["start_time"] + 5.0

        fixed.append(scene)
        expected_start = scene["end_time"]

    if fixed:
        fixed[0]["start_time"] = 0.0
        if fixed[-1]["end_time"] < duration:
            fixed[-1]["end_time"] = duration

    for i, scene in enumerate(fixed):
        scene.setdefault("visual_description", f"Scene {i + 1}")
        scene.setdefault("image_prompt", scene["visual_description"])
        scene.setdefault("mood", "neutral")
        scene.setdefault("camera_movement", "static")

    return fixed
