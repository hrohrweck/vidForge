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
{"scenes": [{"start_time": 0.0, "end_time": 5.0, "narration": "text", "visual_description": "desc", "image_prompt": "prompt", "mood": "mood", "camera_movement": "movement", "seed_image_prompt": "image prompt for seed image generation"}]}

Guidelines:
- Scene duration: 3-15 seconds each — longer scenes allow for richer visual storytelling
- Image prompts: 10-25 words, highly visual
- CRITICAL: Every image_prompt MUST begin with the requested visual style (e.g. "anime style: ...", "cinematic style: ...", "photorealistic: ..."). This ensures visual consistency across all scenes.
- Narration is the text that will be spoken during this scene
- Match mood to the narration content

STORY ARC (distribute scenes across these phases):
- Opening (first 20% of scenes): Establish setting, introduce characters, set the tone
- Development (next 40% of scenes): Build conflict, deepen character arcs, advance the journey
- Climax (next 20% of scenes): Key dramatic moment, peak tension, pivotal action
- Resolution (final 20% of scenes): Satisfying conclusion, aftermath, emotional closure

CONSISTENCY RULES:
- Characters maintain consistent visual description across all scenes — same hair, clothing, build, age
- Color palette, lighting style, and visual mood stay uniform throughout the video
- Each scene's end state flows naturally into the next scene's start state
- Maintain continuity in props, weather, and environment details between adjacent scenes
- If a seed_image_prompt is required, describe the subject in precise visual detail for consistent character/model representation

MODEL GUIDANCE:
The MODEL CAPABILITIES block below (if present) tells you what the video and image models can produce.
- If the video model needs seed images: generate detailed seed_image_prompt fields for each scene
- If the video model needs start+end frames: provide both frame descriptions
- If text-only video: no seed images needed
- If the image model supports specific resolutions or styles: adapt your image_prompt descriptions accordingly
- Adapt your scene descriptions to match what the models can produce

AVATAR CAST MEMBERS:
If provided with a list of avatar cast members (name, gender, bio, role), you may include them in scenes where their presence enhances the narrative. NOT every scene needs avatars — use them naturally as the story demands.
When a scene includes an avatar:
- Include their FULL NAME in the visual_description
- Describe their appearance and actions in the image_prompt
- Use their bio and role to inform how they behave and interact
- Place them naturally within the scene's environment
Example image_prompt with avatar: "cinematic style: Alice (a red-haired detective in a trench coat) examining evidence on a dimly lit desk, dramatic lighting, photorealistic"
Only use avatars that are provided — do NOT invent new characters.

- Camera movements: static, pan_left, pan_right, zoom_in, zoom_out, tilt_up, orbit"""


async def plan_scenes_from_script(
    segments: list[dict[str, Any]],
    duration: float = 30,
    style: str = "realistic",
    avatars_context: str | None = None,
    model_capabilities_context: str | None = None,
    provider: Any | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Plan scenes from parsed script segments.

    Parameters
    ----------
    model_capabilities_context : str | None
        Structured ``MODEL CAPABILITIES`` block produced by
        :func:`~app.services.model_capabilities.build_model_capabilities_context`.
        Appended to the user prompt so the LLM can adapt scene plans to
        the selected video / image model's capabilities.

    Returns a list of scene dicts with keys:
    ``start_time``, ``end_time``, ``narration``, ``visual_description``,
    ``image_prompt``, ``mood``, ``camera_movement``, and optionally
    ``seed_image_prompt``.
    """
    llm = LLMClient(model=model)
    try:
        seg_text = ""
        for i, seg in enumerate(segments):
            narration = seg.get("narration", "")
            visual = seg.get("visual_cue", "")
            seg_text += f"\n{i + 1}. Narration: {narration}"
            if visual:
                seg_text += f"\n   Visual direction: {visual}"

        user_prompt = (
            f"Create a scene plan for a {duration:.0f}-second video.\n"
            f"Style: {style}\n"
        )
        if avatars_context:
            user_prompt += f"\n{avatars_context}\n"
        if model_capabilities_context:
            user_prompt += f"\n{model_capabilities_context}\n\n"
        user_prompt += f"\nScript segments:{seg_text}"

        response = await llm.generate(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.7,
            provider=provider,
        )

        return _parse_response(response, duration)
    finally:
        await llm.close()
        if provider is not None and hasattr(provider, "shutdown"):
            await provider.shutdown()


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
