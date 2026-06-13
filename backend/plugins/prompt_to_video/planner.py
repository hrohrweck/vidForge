"""
Scene planner for the Prompt-to-Video template.

Uses the LLM to break a single prompt into a series of 3-6 second
visual segments, each with its own image prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.services.llm_service import LLMClient
from app.services.media_generator import enforce_min_scene_duration

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a video director. Break the user's prompt into a series of short visual scenes for AI video generation.

Output ONLY valid JSON. Do not include markdown fences, explanations, or reasoning outside the JSON. Do NOT copy placeholder text from the example — fill every field with specific content derived from the user's prompt.

Example shape (fill with your own content, not these placeholders):
{"scenes": [{"start_time": 0.0, "end_time": 5.0, "visual_description": "a specific description of what happens in this scene", "image_prompt": "photorealistic cinematic style: a vivid, detailed description of the scene", "mood": "energetic", "camera_movement": "dynamic tracking shot", "seed_image_prompt": "photorealistic cinematic style: close-up of the subject in the same scene"}], "object_selections": []}

Guidelines:
- Scene duration: respect the max clip duration in the PLANNING CONSTRAINTS. If the total video requires more time, split the story into multiple scenes rather than exceeding the per-clip limit.
- Image prompts: concise, highly visual, and within the model's max prompt length
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

STYLE_PREFIXES = {
    "realistic": "photorealistic cinematic style",
    "anime": "anime style",
    "manga": "manga style",
}


def _style_prefix(style: str) -> str:
    return STYLE_PREFIXES.get(style, f"{style} style")


async def plan_scenes_from_prompt(
    prompt: str,
    duration: float = 10,
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
    original_prompt: str | None = None,
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
        user_prompt = f"Create a scene plan for a {duration}-second video.\nStyle: {style}\n"
        if avatars_context:
            user_prompt += f"\n{avatars_context}\n\n"
        if objects_context:
            user_prompt += f"\n{objects_context}\n\n"
        if reference_capacity_context:
            user_prompt += f"\n{reference_capacity_context}\n\n"
        if model_capabilities_context:
            user_prompt += f"\n{model_capabilities_context}\n\n"
        if constraints_context:
            user_prompt += f"\n{constraints_context}\n\n"
        user_prompt += f"Prompt: {prompt}"
        result: dict[str, Any] = {}

        for attempt in range(2):
            response = await llm.generate(
                prompt=user_prompt,
                system=SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.3,
                provider=provider,
                json_mode=True,
            )
            result = _parse_response(
                response,
                duration,
                original_prompt=original_prompt or prompt,
                style=style,
                max_clip_duration=max_clip_duration,
            )
            if not result.get("_is_fallback"):
                break
            logger.warning(
                "Scene planning produced fallback on attempt %s, retrying...",
                attempt + 1,
            )
            logger.debug("Unparseable planner response:\n%s", response)
            user_prompt += (
                "\n\nIMPORTANT: Output ONLY valid JSON with no extra text, "
                "markdown, or explanations."
            )

        if result.get("_is_fallback"):
            logger.warning("Scene planning failed after retries; using fallback scenes.")

        # Ensure prompts are concise and style-prefixed regardless of parse success.
        max_prompt_chars = image_max_prompt_length or 400
        _ensure_style_prefix(result["scenes"], style)
        await _ensure_concise_prompts(result["scenes"], style, llm, max_chars=max_prompt_chars)

        return result
    finally:
        await llm.close()
        if provider is not None and hasattr(provider, "shutdown"):
            await provider.shutdown()


def _parse_response(
    response: str,
    target_duration: float,
    original_prompt: str | None = None,
    style: str = "realistic",
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

    if not parsed or "scenes" not in parsed:
        logger.warning("LLM response could not be parsed, falling back to single scene")
        return _fallback_result(target_duration, original_prompt, style, max_clip_duration)

    scenes = parsed["scenes"]
    if not scenes or not isinstance(scenes, list):
        logger.warning("LLM response has invalid scenes list, falling back")
        return _fallback_result(target_duration, original_prompt, style, max_clip_duration)

    # Validate each scene is a dictionary
    if not all(isinstance(scene, dict) for scene in scenes):
        logger.warning("LLM response contains non-dict scenes, falling back")
        return _fallback_result(target_duration, original_prompt, style, max_clip_duration)

    if any(_scene_contains_placeholders(scene) for scene in scenes):
        logger.warning("LLM response contains placeholder text, falling back")
        return _fallback_result(target_duration, original_prompt, style, max_clip_duration)

    # Extract object selections if present
    object_selections = parsed.get("object_selections", [])

    # Validate and fix timing
    scenes = _fix_scene_timing(scenes, target_duration)

    return {"scenes": scenes, "object_selections": object_selections}


def _scene_contains_placeholders(scene: dict[str, Any]) -> bool:
    """Return True when a scene echoes example placeholder text."""
    visual = str(scene.get("visual_description", "")).strip().lower()
    image = str(scene.get("image_prompt", "")).strip().lower()
    seed = str(scene.get("seed_image_prompt", "")).strip().lower()
    narration = str(scene.get("narration", "")).strip().lower()

    if visual in {"description", "desc"}:
        return True
    if image in {"prompt"} or "detailed image prompt" in image:
        return True
    if narration in {"text", "narration"}:
        return True
    if "image prompt for seed image generation" in seed:
        return True

    # Example placeholders from the system prompt must not be copied verbatim.
    if visual == "a specific description of what happens in this scene":
        return True
    if image == "photorealistic cinematic style: a vivid, detailed description of the scene":
        return True
    if seed == "photorealistic cinematic style: close-up of the subject in the same scene":
        return True
    if narration == "the spoken narration for this scene":
        return True

    return False


def _clean_llm_response(response: str) -> str:
    """Remove common LLM artifacts (thinking tags, markdown fences, etc.)."""
    text = response.strip()

    # Strip markdown code fences with optional language tag
    if text.startswith("```"):
        start = text.find("\n", 3)
        if start > 0:
            lang_tag = text[3:start].strip().lower()
            if lang_tag in ("json", "", "javascript"):
                end = text.find("```", start + 1)
                if end != -1:
                    text = text[start:end].strip()
                else:
                    text = text[start:].strip()

    text = re.sub(r"【\w+】.*?【/\w+】", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL)

    text = text.strip()
    text = re.sub(
        r"^(Here is|Here are|Okay,|Sure,|Certainly,).*?\n",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def _extract_json_with_scenes(text: str) -> dict | None:
    """Extract a balanced JSON object containing ``scenes`` from arbitrary text."""
    decoder = json.JSONDecoder()
    # First try objects where "scenes" appears at the top level.
    for match in re.finditer(r"\{", text):
        try:
            parsed, _ = decoder.raw_decode(text, match.start())
            if isinstance(parsed, dict) and "scenes" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _fallback_result(
    duration: float,
    original_prompt: str | None = None,
    style: str = "realistic",
    max_clip_duration: float = 5.0,
) -> dict[str, Any]:
    scenes = _fallback_scenes(duration, original_prompt, style, max_clip_duration)
    return {"scenes": scenes, "object_selections": [], "_is_fallback": True}


def _fallback_scenes(
    duration: float,
    original_prompt: str | None = None,
    style: str = "realistic",
    max_clip_duration: float = 5.0,
) -> list[dict[str, Any]]:
    """Create simple evenly-spaced scenes as a fallback.

    Splits the original prompt into sentences so each scene gets a distinct,
    coherent visual description instead of repeating a truncated blob.
    """
    clip_duration = min(max_clip_duration, duration)
    num_scenes = max(1, int(duration / clip_duration))
    actual_duration = duration / num_scenes
    prefix = _style_prefix(style)

    base_description = (original_prompt or "Scene").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", base_description) if s.strip()]
    if not sentences:
        sentences = [base_description]

    scenes: list[dict[str, Any]] = []
    for i in range(num_scenes):
        start_idx = i * len(sentences) // num_scenes
        end_idx = (i + 1) * len(sentences) // num_scenes
        segment_sentences = sentences[start_idx:end_idx]
        if not segment_sentences:
            segment_sentences = [sentences[i % len(sentences)]]

        segment_text = " ".join(segment_sentences)
        image_prompt = f"{prefix}: {segment_text}"

        scenes.append(
            {
                "start_time": round(i * actual_duration, 2),
                "end_time": round((i + 1) * actual_duration, 2),
                "visual_description": segment_text,
                "image_prompt": image_prompt,
                "mood": "neutral",
                "camera_movement": "static",
                "seed_image_prompt": image_prompt,
            }
        )

    return scenes


def _fix_scene_timing(scenes: list[dict], duration: float) -> list[dict[str, Any]]:
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
    fixed = enforce_min_scene_duration(fixed)

    return fixed


def _ensure_style_prefix(scenes: list[dict[str, Any]], style: str) -> None:
    """Prefix each image_prompt with the visual style if it is missing."""
    prefix = _style_prefix(style)
    prefixes = {prefix, style, "photorealistic", "anime", "manga", "cinematic"}
    for scene in scenes:
        ip = scene.get("image_prompt", "")
        if not ip:
            continue
        if not any(ip.lower().startswith(p) for p in prefixes):
            scene["image_prompt"] = f"{prefix}: {ip}"
            if "seed_image_prompt" in scene:
                scene["seed_image_prompt"] = f"{prefix}: {scene['seed_image_prompt']}"


async def _ensure_concise_prompts(
    scenes: list[dict[str, Any]],
    style: str,
    llm: LLMClient,
    max_words: int = 40,
    max_chars: int = 400,
) -> None:
    """Ask the LLM to shorten any scene prompt that is too long.

    This keeps the prompts usable for image/video models without blunt truncation.
    """
    prefix = _style_prefix(style)
    long_scenes: list[dict[str, Any]] = []
    for scene in scenes:
        ip = scene.get("image_prompt", "")
        words = len(ip.split())
        if words > max_words or len(ip) > max_chars:
            long_scenes.append(scene)

    if not long_scenes:
        return

    system = (
        "You shorten image-generation prompts. Rewrite the prompt to be "
        "concise (about 15-25 words) while keeping the key subject, setting, "
        "mood, and visual style. Preserve the existing style prefix. "
        "Output ONLY the shortened prompt, nothing else."
    )

    async def _shorten(scene: dict[str, Any]) -> None:
        ip = scene["image_prompt"]
        user = (
            f"Rewrite this image prompt to be concise (15-25 words). "
            f"Keep the style prefix '{prefix}'.\n\n"
            f"Prompt: {ip}\n\nShortened prompt:"
        )
        try:
            shortened = await llm.generate(
                prompt=user,
                system=system,
                max_tokens=256,
                temperature=0.3,
            )
            shortened = shortened.strip().strip('"').strip()
            if shortened:
                if not any(
                    shortened.lower().startswith(p)
                    for p in {prefix, style, "photorealistic", "anime", "manga", "cinematic"}
                ):
                    shortened = f"{prefix}: {shortened}"
                scene["image_prompt"] = shortened
                if scene.get("seed_image_prompt"):
                    scene["seed_image_prompt"] = shortened
        except Exception:
            logger.warning("Failed to shorten scene prompt", exc_info=True)

    await asyncio.gather(*(_shorten(scene) for scene in long_scenes))
