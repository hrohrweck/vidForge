import json
import re
from typing import Any

from app.services.llm_service import LLMClient


class MusicVideoPlannerError(Exception):
    pass


class MusicVideoPlanner:
    SYSTEM_PROMPT = """You are a music video director. Analyze lyrics and create a visual story with distinct scenes.

Output ONLY valid JSON:
{"scenes": [{"scene_number": 1, "start_time": 0.0, "end_time": 10.0, "lyrics_segment": "lyrics", "visual_description": "desc", "image_prompt": "prompt", "mood": "neutral", "camera_movement": "static"}], "total_scenes": 1, "summary": "summary"}

Guidelines:
- Respect the PLANNING CONSTRAINTS block provided in the user prompt for max scene duration and prompt length.
- Match mood to lyrics emotion
- Image prompts: concise, highly visual, and within the model's max prompt length
- CRITICAL: Every image_prompt MUST begin with the requested visual style (e.g. "anime style: ...", "cinematic style: ...", "photorealistic: ..."). This ensures visual consistency across all scenes.
- First scene sets mood, last provides closure

AVATAR CAST MEMBERS:
If provided with a list of avatar cast members (name, gender, bio, role), you may include them in scenes where their presence enhances the narrative. NOT every scene needs avatars — use them naturally as the story demands.
When a scene includes an avatar:
- Include their FULL NAME in the visual_description
- Describe their appearance and actions in the image_prompt
- Use their bio and role to inform how they behave and interact
- Place them naturally within the scene's environment
Example image_prompt with avatar: "cinematic style: Alice (a red-haired detective in a trench coat) examining evidence on a dimly lit desk, dramatic lighting, photorealistic"
Only use avatars that are provided — do NOT invent new characters."""

    def __init__(self, llm_client: LLMClient | None = None, provider: Any | None = None, model: str | None = None):
        self.llm = llm_client or LLMClient(model=model)
        self.provider = provider

    async def close(self) -> None:
        await self.llm.close()
        if self.provider is not None and hasattr(self.provider, "shutdown"):
            await self.provider.shutdown()

    async def plan_music_video(
        self,
        lyrics: dict[str, Any],
        duration: float,
        style: str = "realistic",
        model_capabilities_context: str | None = None,
        constraints_context: str | None = None,
        max_clip_duration: float = 5.0,
        image_max_prompt_length: int | None = None,
    ) -> dict[str, Any]:
        lyrics_text = lyrics.get("full_text", "")
        lines = lyrics.get("lines", [])

        line_info = self._build_line_info(lines)

        prompt = self._build_planning_prompt(
            lyrics_text,
            line_info,
            duration,
            style,
            model_capabilities_context=model_capabilities_context,
            constraints_context=constraints_context,
        )

        response = await self.llm.generate(
            prompt=prompt,
            system=self.SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.7,
            provider=self.provider,
        )

        if not response:
            raise MusicVideoPlannerError("Empty response from LLM - check Ollama logs")

        parsed = self._parse_response(response, duration)
        scenes = self._enforce_max_scene_duration(
            parsed.get("scenes", []), duration, max_clip_duration
        )

        if image_max_prompt_length:
            for scene in scenes:
                for key in ("image_prompt", "visual_description"):
                    value = scene.get(key, "")
                    if value and len(value) > image_max_prompt_length:
                        scene[key] = value[:image_max_prompt_length].rsplit(" ", 1)[0]

        parsed["scenes"] = scenes
        parsed["total_scenes"] = len(scenes)
        return parsed

    def _parse_response(self, response: str, duration: float) -> dict[str, Any]:
        try:
            response = response.strip()

            if not response or response == "null":
                raise MusicVideoPlannerError(f"Response is null/empty after strip: {repr(response[:100])}")

            if response.startswith("```"):
                parts = response.split("```")
                response = parts[1] if len(parts) > 1 and "scenes" in parts[1] else response
                if len(parts) > 2:
                    response = parts[2] if "scenes" in parts[2] else parts[1]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip()

            if not response or response == "null":
                raise MusicVideoPlannerError(f"Response is null/empty after cleanup: {repr(response[:100])}")

            parsed = None

            # Try 1: Direct JSON parse (works for complete responses)
            for candidate in [response, response.replace("```json", "").replace("```", "")]:
                candidate = candidate.strip()
                if candidate.startswith("{") and "scenes" in candidate:
                    try:
                        parsed = json.loads(candidate)
                        break
                    except json.JSONDecodeError:
                        pass

            # Try 2: Regex extraction (for incomplete JSON at the end)
            if not parsed:
                json_match = re.search(r'\{.*?"scenes".*?\}', response, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass

            # Try 3: Brace-matching - find largest valid JSON object (handles truncation)
            if not parsed:
                parsed = self._extract_json_by_brace_matching(response)

            # Try 4: Extract complete scenes from truncated response
            if not parsed:
                parsed = self._extract_complete_scenes(response)

            # Try 5: Repair truncated JSON by closing open strings/brackets
            if not parsed:
                repaired = self._repair_truncated_json(response)
                if repaired:
                    try:
                        parsed = json.loads(repaired)
                    except json.JSONDecodeError:
                        pass

            if not parsed:
                raise MusicVideoPlannerError(f"Failed to parse LLM response: {repr(response[:300])}")

            return self._validate_and_fix_scenes(parsed, duration)
        except json.JSONDecodeError:
            raise MusicVideoPlannerError(f"Failed to parse LLM response: {repr(response[:200])}")

    def _extract_json_by_brace_matching(self, response: str) -> dict[str, Any] | None:
        """Extract JSON by finding balanced braces, handling truncated responses."""
        start = response.find("{")
        if start == -1:
            return None

        # Try progressively larger portions, looking for balanced braces
        for end in range(start + 1, len(response) + 1):
            candidate = response[start:end]
            try:
                parsed = json.loads(candidate)
                if "scenes" in parsed or "total_scenes" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        return None

    def _extract_complete_scenes(self, response: str) -> dict[str, Any] | None:
        """Extract individual complete scene objects from a truncated response."""
        # Find all complete scene objects using regex
        # A complete scene has all required fields and closes properly
        scene_pattern = r'\{\s*"scene_number"\s*:\s*\d+\s*,\s*"start_time"\s*:\s*[\d.]+\s*,\s*"end_time"\s*:\s*[\d.]+\s*,\s*"lyrics_segment"\s*:\s*"[^"]*"\s*,\s*"visual_description"\s*:\s*"[^"]*"'

        scenes = []
        for match in re.finditer(scene_pattern, response):
            start_idx = match.start()
            brace_count = 1
            for i in range(start_idx + 1, len(response)):
                if response[i] == '{':
                    brace_count += 1
                elif response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            scene = json.loads(response[start_idx:i+1])
                            scenes.append(scene)
                        except json.JSONDecodeError:
                            pass
                        break

        if scenes:
            return {
                "scenes": scenes,
                "total_scenes": len(scenes),
                "summary": f"Extracted {len(scenes)} scenes from truncated response",
            }

        return None

    def _repair_truncated_json(self, response: str) -> str | None:
        """Repair truncated JSON by closing open strings, objects, and arrays."""
        # Find the start of the JSON
        start = response.find("{")
        if start == -1:
            return None

        json_str = response[start:]

        in_string = False
        escape_next = False
        open_braces = 0
        open_brackets = 0
        repaired_chars = []

        for char in json_str:
            if escape_next:
                repaired_chars.append(char)
                escape_next = False
                continue

            if char == '\\':
                repaired_chars.append(char)
                escape_next = True
                continue

            if char == '"' and not in_string:
                in_string = True
                repaired_chars.append(char)
            elif char == '"' and in_string:
                in_string = False
                repaired_chars.append(char)
            elif char == '\n' and in_string:
                repaired_chars.append('\\')
                repaired_chars.append('n')
            elif char == '\n' and not in_string:
                repaired_chars.append(' ')
            elif not in_string:
                if char == '{':
                    open_braces += 1
                    repaired_chars.append(char)
                elif char == '}':
                    open_braces -= 1
                    repaired_chars.append(char)
                elif char == '[':
                    open_brackets += 1
                    repaired_chars.append(char)
                elif char == ']':
                    open_brackets -= 1
                    repaired_chars.append(char)
                else:
                    repaired_chars.append(char)
            else:
                repaired_chars.append(char)

        # If we're in a string, close it
        if in_string:
            repaired_chars.append('"')

        # Close any open objects/arrays
        if open_braces > 0:
            if open_braces >= 2:
                repaired_chars.append('}')
            if open_brackets > 0:
                repaired_chars.append(']')
            repaired_chars.append('}')

        repaired = ''.join(repaired_chars)

        # Validate the repaired JSON
        try:
            parsed = json.loads(repaired)
            if "scenes" in parsed and len(parsed.get("scenes", [])) > 0:
                return repaired
        except json.JSONDecodeError:
            pass

        return None

    def _build_line_info(self, lines: list[dict[str, Any]]) -> str:
        line_info_parts = []
        for line in lines[:30]:
            text = line.get("text", "")
            start = line.get("start", 0)
            end = line.get("end", 0)
            line_info_parts.append(f"[{start:.1f}s-{end:.1f}s] {text}")
        return "\n".join(line_info_parts)

    def _build_planning_prompt(
        self,
        lyrics_text: str,
        line_info: str,
        duration: float,
        style: str,
        model_capabilities_context: str | None = None,
        constraints_context: str | None = None,
    ) -> str:
        prompt = f"""Create a scene-by-scene plan for a music video.

Song duration: {duration} seconds
Visual style: {style}

Lyrics:
{lyrics_text}

Timestamped lyrics (for reference):
{line_info}"""
        if model_capabilities_context:
            prompt += f"\n\n{model_capabilities_context}"
        if constraints_context:
            prompt += f"\n\n{constraints_context}"
        prompt += "\n\nCreate a detailed scene plan in JSON format."
        return prompt

    def _validate_and_fix_scenes(self, parsed: dict[str, Any], duration: float) -> dict[str, Any]:
        if "scenes" not in parsed:
            parsed["scenes"] = []
        if "total_scenes" not in parsed:
            parsed["total_scenes"] = len(parsed["scenes"])
        if "summary" not in parsed:
            parsed["summary"] = "Music video plan"

        scenes = parsed["scenes"]
        if not scenes:
            return parsed

        scenes.sort(key=lambda s: s.get("start_time", 0))

        fixed_scenes = []
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

            fixed_scenes.append(scene)
            expected_start = scene["end_time"]

        if fixed_scenes and fixed_scenes[-1]["end_time"] < duration:
            fixed_scenes[-1]["end_time"] = duration

        if fixed_scenes and fixed_scenes[0]["start_time"] > 0:
            fixed_scenes[0]["start_time"] = 0.0

        for i, scene in enumerate(fixed_scenes):
            scene["scene_number"] = i + 1

        # Enforce minimum scene duration
        from app.services.media_generator import enforce_min_scene_duration
        fixed_scenes = enforce_min_scene_duration(fixed_scenes)

        parsed["scenes"] = fixed_scenes
        parsed["total_scenes"] = len(fixed_scenes)

        return parsed

    def _enforce_max_scene_duration(
        self,
        scenes: list[dict[str, Any]],
        duration: float,
        max_clip_duration: float,
    ) -> list[dict[str, Any]]:
        """Split any scene longer than max_clip_duration into chained sub-scenes."""
        if max_clip_duration <= 0:
            max_clip_duration = 5.0
        result: list[dict[str, Any]] = []
        for scene in scenes:
            scene_duration = scene.get("end_time", duration) - scene.get("start_time", 0)
            if scene_duration <= max_clip_duration:
                result.append(scene)
                continue
            start = scene.get("start_time", 0)
            end = scene.get("end_time", duration)
            sub_index = 0
            while start < end:
                sub_end = min(end, start + max_clip_duration)
                sub_scene = dict(scene)
                sub_scene["start_time"] = round(start, 2)
                sub_scene["end_time"] = round(sub_end, 2)
                if sub_index > 0:
                    sub_scene["visual_description"] = (
                        f"{scene.get('visual_description', '')} (continuation {sub_index + 1})"
                    )
                    sub_scene["image_prompt"] = (
                        f"{scene.get('image_prompt', '')} (continuation {sub_index + 1})"
                    )
                result.append(sub_scene)
                start = sub_end
                sub_index += 1
        for i, s in enumerate(result):
            s["scene_number"] = i + 1
        return result
