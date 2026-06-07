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
{"scenes": [{"start_time": 0.0, "end_time": 5.0, "visual_description": "description", "image_prompt": "detailed image prompt", "mood": "mood", "camera_movement": "movement", "seed_image_prompt": "image prompt for seed image generation"}]}

Guidelines:
- Scene duration: 3-15 seconds each — longer scenes allow for richer visual storytelling
- Image prompts: 10-25 words, highly visual, specific
- CRITICAL: Every image_prompt MUST begin with the requested visual style (e.g. "anime style: ...", "cinematic style: ...", "photorealistic: ..."). This ensures visual consistency across all scenes.
- Ensure smooth narrative flow between scenes
- Match mood to the content

STORY ARC (distribute scenes across these phases):
- Opening (first 20% of scenes): Establish setting, introduce characters, set the tone
- Development (next 40% of scenes): Build conflict, deepen character arcs, advance the journey
- Climax (next 20% of scenes): Key dramatic moment, peak tension, pivotal action
- Resolution (final 20% of scenes): Satisfying conclusion, aftermath, emotional closure

OBJECT PRIORITY RULES:
The OBJECT CATALOG lists recurring items/vehicles/tools/props in the story.
The REFERENCE CAPACITY tells you how many can receive reference images.

Ranking: Assign importance to each object:
- Critical (score 0.8-1.0): Central to story, appears in 3+ scenes
- Important (score 0.5-0.7): Appears in 2+ scenes, story-relevant
- Incidental (score 0.1-0.4): Mentioned once, can be described in words

Select up to {available_slots} objects for reference images (highest scored).
For selected objects: output seed_image_prompt describing appearance + scene context.
For remaining objects: include precise visual descriptions in visual_description only.

OBJECT CONSISTENCY: Once an object's visual properties are established
(color, shape, size, material), NEVER change them across scenes.

Output object selections in your JSON as an "object_selections" key:
[{"object_name": "...", "importance_score": 0.9,
  "seed_image_prompt": "detailed prompt for reference image",
  "scenes": [1, 3, 5]}]

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

- Camera movements: static, pan_left, pan_right, zoom_in, zoom_out, tilt_up, orbit
- Total duration should match the requested duration"""


async def plan_scenes_from_prompt(
    prompt: str,
    duration: float = 10,
    style: str = "realistic",
    avatars_context: str | None = None,
    model_capabilities_context: str | None = None,
    objects_context: str | None = None,
    reference_capacity_context: str | None = None,
    provider: Any | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Plan scenes from a single text prompt.

    Parameters
    ----------
    model_capabilities_context : str | None
        Structured ``MODEL CAPABILITIES`` block produced by
        :func:`~app.services.model_capabilities.build_model_capabilities_context`.
        Appended to the user prompt so the LLM can adapt scene plans to
        the selected video / image model's capabilities.
    objects_context : str | None
        Structured ``OBJECT CATALOG`` block produced by
        :func:`~app.services.avatar_prompt_builder.build_object_catalog_string`.
    reference_capacity_context : str | None
        Structured ``REFERENCE CAPACITY`` block produced by
        :func:`~app.services.model_capabilities.build_reference_capacity_context`.

    Returns a dict with keys:
    ``scenes`` — list of scene dicts (start_time, end_time, visual_description,
    image_prompt, mood, camera_movement, seed_image_prompt)
    ``object_selections`` — list of object priority selections
    """
    llm = LLMClient(model=model)
    try:
        user_prompt = (
            f"Create a scene plan for a {duration}-second video.\n"
            f"Style: {style}\n"
        )
        if avatars_context:
            user_prompt += f"\n{avatars_context}\n\n"
        if objects_context:
            user_prompt += f"\n{objects_context}\n\n"
        if reference_capacity_context:
            user_prompt += f"\n{reference_capacity_context}\n\n"
        if model_capabilities_context:
            user_prompt += f"\n{model_capabilities_context}\n\n"
        user_prompt += f"Prompt: {prompt}"
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


def _parse_response(response: str, target_duration: float) -> dict[str, Any]:
    """Parse LLM response into a dict with ``scenes`` and ``object_selections`` keys."""
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
        return _fallback_result(target_duration)

    scenes = parsed["scenes"]
    if not scenes:
        return _fallback_result(target_duration)

    # Extract object selections if present
    object_selections = parsed.get("object_selections", [])

    # Validate and fix timing
    scenes = _fix_scene_timing(scenes, target_duration)

    return {"scenes": scenes, "object_selections": object_selections}


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


def _fallback_result(duration: float) -> dict[str, Any]:
    scenes = _fallback_scenes(duration)
    return {"scenes": scenes, "object_selections": []}


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
        scene.setdefault("seed_image_prompt", scene["image_prompt"])

    # Enforce minimum scene duration
    from app.services.media_generator import enforce_min_scene_duration
    fixed = enforce_min_scene_duration(fixed)

    return fixed
