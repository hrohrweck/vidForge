"""
Scene planner for the Script-to-Video template.

Uses the LLM to convert script segments into detailed visual scene
descriptions with image prompts.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from app.services.llm_service import LLMClient
from app.services.media_generator import enforce_min_scene_duration

from ..prompt_to_video.planner import (
    _clean_llm_response,
    _ensure_concise_prompts,
    _ensure_style_prefix,
    _extract_json_with_scenes,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a video director. Convert script segments into visual scenes for AI video generation.

Output ONLY valid JSON:
{"scenes": [{"start_time": 0.0, "end_time": 5.0, "narration": "text", "visual_description": "desc", "image_prompt": "prompt", "mood": "mood", "camera_movement": "movement", "seed_image_prompt": "image prompt for seed image generation"}]}

Guidelines:
- Scene duration: respect the max clip duration in the PLANNING CONSTRAINTS. If the total video requires more time, split the story into multiple scenes rather than exceeding the per-clip limit.
- Image prompts: concise, highly visual, and within the model's max prompt length
- CRITICAL: Every image_prompt MUST begin with the requested visual style (e.g. "anime style: ...", "cinematic style: ...", "photorealistic: ..."). This ensures visual consistency across all scenes.
- Narration is the text that will be spoken during this scene
- Match mood to the narration content

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

- Camera movements: static, pan_left, pan_right, zoom_in, zoom_out, tilt_up, orbit"""


async def plan_scenes_from_script(
    segments: list[dict[str, Any]],
    duration: float = 30,
    style: str = "realistic",
    avatars_context: str | None = None,
    model_capabilities_context: str | None = None,
    constraints_context: str | None = None,
    objects_context: str | None = None,
    reference_capacity_context: str | None = None,
    provider: Any | None = None,
    model: str | None = None,
    max_clip_duration: float = 5.0,
    image_max_prompt_length: int | None = None,
) -> dict[str, Any]:
    """Plan scenes from parsed script segments.

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
    ``scenes`` — list of scene dicts (start_time, end_time, narration,
    visual_description, image_prompt, mood, camera_movement, seed_image_prompt)
    ``object_selections`` — list of object priority selections
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
        if objects_context:
            user_prompt += f"\n{objects_context}\n"
        if reference_capacity_context:
            user_prompt += f"\n{reference_capacity_context}\n"
        if model_capabilities_context:
            user_prompt += f"\n{model_capabilities_context}\n\n"
        if constraints_context:
            user_prompt += f"\n{constraints_context}\n\n"
        user_prompt += f"\nScript segments:{seg_text}"
        result: dict[str, Any] = {}

        for attempt in range(2):
            response = await llm.generate(
                prompt=user_prompt,
                system=SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.7,
                provider=provider,
            )

            result = _parse_response(
                response,
                duration,
                original_segments=segments,
                max_clip_duration=max_clip_duration,
            )
            if not result.get("_is_fallback"):
                break
            logger.warning("Scene planning produced fallback on attempt %s, retrying...", attempt + 1)
            user_prompt += "\n\nIMPORTANT: Output ONLY valid JSON with no extra text, markdown, or explanations."

        max_prompt_chars = image_max_prompt_length or 400
        _ensure_style_prefix(result["scenes"], style)
        await _ensure_concise_prompts(
            result["scenes"], style, llm, max_chars=max_prompt_chars
        )

        return result
    finally:
        await llm.close()
        if provider is not None and hasattr(provider, "shutdown"):
            await provider.shutdown()


def _parse_response(
    response: str,
    target_duration: float,
    original_segments: list[dict[str, Any]] | None = None,
    max_clip_duration: float = 5.0,
) -> dict[str, Any]:
    """Parse LLM response into a dict with ``scenes`` and ``object_selections`` keys."""
    cleaned = _clean_llm_response(response)

    parsed = _extract_json_with_scenes(cleaned)

    if not parsed:
        candidates = [
            cleaned,
            cleaned.replace("```json", "").replace("```", ""),
            re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL),
            re.sub(r"【.*?】", "", cleaned),
            re.sub(r"\*\*.*?\*\*", "", cleaned),
        ]
        for candidate in candidates:
            parsed = _extract_json_with_scenes(candidate)
            if parsed:
                break

    if not parsed:
        logger.warning("Could not parse LLM scene plan, using fallback")
        segments_count = len(original_segments) if original_segments else max(1, int(target_duration / max_clip_duration))
        return _fallback_result(
            segments_count,
            original_segments,
            max_clip_duration,
            target_duration=target_duration,
        )

    scenes = parsed.get("scenes", [])
    if not scenes or not isinstance(scenes, list):
        logger.warning("LLM response has invalid scenes list, falling back")
        segments_count = len(original_segments) if original_segments else max(1, int(target_duration / max_clip_duration))
        return _fallback_result(
            segments_count,
            original_segments,
            max_clip_duration,
            target_duration=target_duration,
        )

    # Validate each scene is a dictionary
    if not all(isinstance(scene, dict) for scene in scenes):
        logger.warning("LLM response contains non-dict scenes, falling back")
        segments_count = len(original_segments) if original_segments else max(1, int(target_duration / max_clip_duration))
        return _fallback_result(
            segments_count,
            original_segments,
            max_clip_duration,
            target_duration=target_duration,
        )

    # Extract object selections if present
    object_selections = parsed.get("object_selections", [])

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
    scenes = enforce_min_scene_duration(scenes)

    return {"scenes": scenes, "object_selections": object_selections}


def _fallback_result(
    segments_count: int,
    original_segments: list[dict[str, Any]] | None = None,
    max_clip_duration: float = 5.0,
    target_duration: float | None = None,
) -> dict[str, Any]:
    if target_duration is not None:
        segments_count = min(
            segments_count,
            max(1, math.ceil(target_duration / max_clip_duration)),
        )
    scenes = _fallback_scenes(segments_count, original_segments, max_clip_duration)
    if target_duration is not None and scenes:
        scenes[-1]["end_time"] = target_duration
    return {"scenes": scenes, "object_selections": [], "_is_fallback": True}


def _fallback_scenes(
    segments_count: int,
    original_segments: list[dict[str, Any]] | None = None,
    max_clip_duration: float = 5.0,
) -> list[dict[str, Any]]:
    def _seg_desc(i: int) -> str:
        if original_segments and i < len(original_segments):
            narration = original_segments[i].get("narration", "").strip()
            if narration:
                return narration if len(narration) <= 100 else narration[:100] + "..."
        return f"Scene {i + 1}"

    return [
        {
            "start_time": i * max_clip_duration,
            "end_time": (i + 1) * max_clip_duration,
            "narration": original_segments[i].get("narration", "") if original_segments and i < len(original_segments) else "",
            "visual_description": _seg_desc(i),
            "image_prompt": f"Visual scene {i + 1}: {_seg_desc(i)}",
            "mood": "neutral",
            "camera_movement": "static",
        }
        for i in range(segments_count)
    ]
