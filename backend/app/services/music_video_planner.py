import json
from typing import Any

from app.services.llm_service import LLMClient


class MusicVideoPlannerError(Exception):
    pass


class MusicVideoPlanner:
    SYSTEM_PROMPT = """You are an expert music video director. Your job is to analyze song lyrics and create a compelling visual story with distinct scenes.

You must output valid JSON only - no explanations or additional text.

For the given lyrics, you need to:
1. Divide the lyrics into logical scenes (usually verse/chorus changes, or every 10-30 seconds)
2. For each scene, generate a detailed image generation prompt
3. Ensure visual continuity across scenes while showing progression

Output format must be:
{
  "scenes": [
    {
      "scene_number": 1,
      "start_time": 0.0,
      "end_time": 10.0,
      "lyrics_segment": "First few lines of lyrics for this scene",
      "visual_description": "Detailed description of what to show in this scene",
      "image_prompt": "A concise prompt for AI image generation (for first frame)",
      "mood": "energetic|calm|melancholic|happy|mysterious|etc",
      "camera_movement": "static|pan_left|pan_right|zoom_in|zoom_out|dolly|etc"
    }
  ],
  "total_scenes": N,
  "summary": "Brief 1-2 sentence summary of the video concept"
}

Guidelines:
- Scene duration: usually 5-15 seconds each
- Match visual mood to lyrics emotion
- Use specific camera movements for dynamic feel
- Image prompts should be 10-30 words, descriptive but not overly complex
- First scene sets the mood, last scene provides closure
- Consider beat drops, chorus repetitions, and song structure"""

    def __init__(self):
        self.llm = LLMClient()

    async def close(self) -> None:
        await self.llm.close()

    async def plan_music_video(
        self,
        lyrics: dict[str, Any],
        duration: float,
        style: str = "realistic",
    ) -> dict[str, Any]:
        lyrics_text = lyrics.get("full_text", "")
        lines = lyrics.get("lines", [])

        line_info = self._build_line_info(lines)

        prompt = self._build_planning_prompt(lyrics_text, line_info, duration, style)

        response = await self.llm.generate(
            prompt=prompt,
            system=self.SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.7,
        )

        try:
            parsed = json.loads(response)
            return self._validate_and_fix_scenes(parsed, duration)
        except json.JSONDecodeError as e:
            raise MusicVideoPlannerError(f"Failed to parse LLM response: {e}")

    def _build_line_info(self, lines: list[dict[str, Any]]) -> str:
        line_info_parts = []
        for line in lines[:30]:
            text = line.get("text", "")
            start = line.get("start", 0)
            end = line.get("end", 0)
            line_info_parts.append(f"[{start:.1f}s-{end:.1f}s] {text}")
        return "\n".join(line_info_parts)

    def _build_planning_prompt(
        self, lyrics_text: str, line_info: str, duration: float, style: str
    ) -> str:
        return f"""Create a scene-by-scene plan for a music video.

Song duration: {duration} seconds
Visual style: {style}

Lyrics:
{lyrics_text}

Timestamped lyrics (for reference):
{line_info}

Create a detailed scene plan with {max(3, int(duration / 10))}-{min(15, int(duration / 7))} scenes.
Ensure each scene has:
- Accurate timing based on the lyrics timestamps
- A distinct visual concept that matches the lyrics mood
- An image generation prompt for the first frame
- Appropriate camera movement for the scene's energy

Output ONLY valid JSON."""

    def _validate_and_fix_scenes(
        self, parsed: dict[str, Any], total_duration: float
    ) -> dict[str, Any]:
        scenes = parsed.get("scenes", [])

        if not scenes:
            raise MusicVideoPlannerError("LLM returned no scenes")

        fixed_scenes = []
        for i, scene in enumerate(scenes):
            fixed_scene = {
                "scene_number": scene.get("scene_number", i + 1),
                "start_time": max(0.0, scene.get("start_time", i * (total_duration / len(scenes)))),
                "end_time": min(
                    total_duration,
                    scene.get("end_time", (i + 1) * (total_duration / len(scenes))),
                ),
                "lyrics_segment": scene.get("lyrics_segment", ""),
                "visual_description": scene.get("visual_description", ""),
                "image_prompt": scene.get("image_prompt", ""),
                "mood": scene.get("mood", "neutral"),
                "camera_movement": scene.get("camera_movement", "static"),
            }
            fixed_scenes.append(fixed_scene)

        sorted_scenes = sorted(fixed_scenes, key=lambda s: s["start_time"])

        for i in range(len(sorted_scenes) - 1):
            sorted_scenes[i]["end_time"] = min(
                sorted_scenes[i]["end_time"], sorted_scenes[i + 1]["start_time"]
            )

        sorted_scenes[-1]["end_time"] = total_duration

        for i, scene in enumerate(sorted_scenes):
            scene["scene_number"] = i + 1

        return {
            "scenes": sorted_scenes,
            "total_scenes": len(sorted_scenes),
            "summary": parsed.get("summary", ""),
            "duration": total_duration,
        }

    async def regenerate_scene_prompt(
        self,
        scene: dict[str, Any],
        lyrics_context: str,
        style: str = "realistic",
    ) -> dict[str, Any]:
        prompt = f"""Regenerate the image prompt for this scene.

Scene details:
- Start time: {scene.get('start_time')}s
- End time: {scene.get('end_time')}s
- Lyrics: {scene.get('lyrics_segment')}
- Current visual description: {scene.get('visual_description')}
- Current mood: {scene.get('mood')}
- Camera movement: {scene.get('camera_movement')}
- Style: {style}

Provide a new image_prompt that better captures the scene's essence.
Output ONLY valid JSON with just the updated fields:
{{
  "image_prompt": "new prompt here",
  "visual_description": "updated description",
  "mood": "updated mood if different"
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            max_tokens=512,
            temperature=0.7,
        )

        try:
            updated = json.loads(response)
            return {**scene, **updated}
        except json.JSONDecodeError:
            return scene
