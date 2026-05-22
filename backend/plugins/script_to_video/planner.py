"""
Scene planner for the Script-to-Video template.

Uses the LLM to convert script segments into detailed visual scene
descriptions with image prompts.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm_service import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a video director. Convert script segments into visual scenes for AI video generation.

Each scene should be 3-15 seconds long. Output ONLY valid JSON:
{"scenes": [{"start_time": 0.0, "end_time": 5.0, "narration": "text", "visual_description": "desc", "image_prompt": "prompt", "mood": "mood", "camera_movement": "movement"}]}

Guidelines:
- Scene duration: 3-15 seconds each — longer scenes allow for richer visual storytelling
- Image prompts: 10-25 words, highly visual
- CRITICAL: Every image_prompt MUST begin with the requested visual style (e.g. "anime style: ...", "cinematic style: ...", "photorealistic: ..."). This ensures visual consistency across all scenes.
- Narration is the text that will be spoken during this scene
- Match mood to the narration content
- Camera movements: static, pan_left, pan_right, zoom_in, zoom_out, tilt_up, orbit"""


async def plan_scenes_from_script(
    segments: list[dict[str, Any]],
    duration: float = 30,
    style: str = "realistic",
) -> list[dict[str, Any]]:
    """Plan scenes from parsed script segments."""
    llm = LLMClient()
    try:
        # Build segment summary
        seg_text = ""
        for i, seg in enumerate(segments):
            narration = seg.get("narration", "")
            visual = seg.get("visual_cue", "")
            seg_text += f"\n{i + 1}. Narration: {narration}"
            if visual:
                seg_text += f"\n   Visual direction: {visual}"

        user_prompt = (
            f"Create a scene plan for a {duration:.0f}-second video.\n"
            f"Style: {style}\n\n"
            f"Script segments:{seg_text}"
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
    """Parse LLM response into scene list."""
    response = response.strip()

    if response.startswith("```"):
        parts = response.split("```")
        for part in parts:
            if "scenes" in part:
                response = part.replace("json", "", 1).strip()
                break

    parsed = None
    for candidate in [response, response.replace("```json", "").replace("```", "")]:
        candidate = candidate.strip()
        if candidate.startswith("{") and "scenes" in candidate:
            try:
                parsed = json.loads(candidate)
                break
            except json.JSONDecodeError:
                pass

    if not parsed:
        m = re.search(r'\{.*?"scenes".*?\}', response, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    if not parsed:
        logger.warning("Could not parse LLM scene plan, using fallback")
        return _fallback_scenes(segments_count=max(1, int(target_duration / 5)))

    scenes = parsed.get("scenes", [])
    if not scenes:
        return _fallback_scenes(max(1, int(target_duration / 5)))

    # Fix timing
    scenes.sort(key=lambda s: s.get("start_time", 0))
    for i, s in enumerate(scenes):
        s.setdefault("visual_description", f"Scene {i + 1}")
        s.setdefault("image_prompt", s["visual_description"])
        s.setdefault("mood", "neutral")
        s.setdefault("camera_movement", "static")
        s.setdefault("narration", "")
        if i == len(scenes) - 1:
            s["end_time"] = target_duration

    # Enforce minimum scene duration
    from app.services.media_generator import enforce_min_scene_duration
    scenes = enforce_min_scene_duration(scenes)

    return scenes


def _fallback_scenes(segments_count: int) -> list[dict[str, Any]]:
    return [
        {
            "start_time": i * 5.0,
            "end_time": (i + 1) * 5.0,
            "narration": "",
            "visual_description": f"Scene {i + 1}",
            "image_prompt": f"Visual scene {i + 1}",
            "mood": "neutral",
            "camera_movement": "static",
        }
        for i in range(segments_count)
    ]
