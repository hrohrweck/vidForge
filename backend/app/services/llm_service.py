import asyncio
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, base_url: str | None = None, model: str = "llama3.2"):
        self.base_url = base_url or settings.ollama_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=120.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPError as e:
            raise LLMError(f"LLM request failed: {e}")

    async def generate_with_context(
        self,
        prompt: str,
        context: dict[str, Any],
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        formatted_prompt = prompt
        for key, value in context.items():
            formatted_prompt = formatted_prompt.replace(f"{{{key}}}", str(value))

        return await self.generate(
            formatted_prompt, system=system, max_tokens=max_tokens, temperature=temperature
        )


class PromptEnhancer:
    SYSTEM_PROMPT = """You are a video generation prompt enhancer. Your job is to take a user's video description and enhance it with visual details that will help create better videos.

Rules:
- Keep the core idea intact
- Add specific visual details (lighting, camera angles, colors, movements)
- Add mood and atmosphere descriptions
- Keep the enhanced prompt concise (2-3 sentences max)
- Don't add dialogue or text overlays unless specifically requested
- Focus on what can be visually shown

Output only the enhanced prompt, nothing else."""

    STYLE_PROMPTS = {
        "realistic": "photorealistic, cinematic lighting, natural colors, detailed textures, high quality footage",
        "anime": "anime style, vibrant colors, clean lines, expressive characters, dynamic animation",
        "manga": "manga style, black and white with dramatic shading, strong contrasts, stylized",
    }

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    async def close(self) -> None:
        await self.llm.close()

    async def enhance(
        self,
        prompt: str,
        style: str = "realistic",
        additional_context: str = "",
    ) -> str:
        style_suffix = self.STYLE_PROMPTS.get(style, "")

        user_prompt = f"Enhance this video prompt for {style} style:\n\n{prompt}"
        if additional_context:
            user_prompt += f"\n\nAdditional context: {additional_context}"

        enhanced = await self.llm.generate(
            prompt=user_prompt,
            system=self.SYSTEM_PROMPT,
            max_tokens=256,
            temperature=0.7,
        )

        enhanced = enhanced.strip()
        if enhanced.startswith('"') and enhanced.endswith('"'):
            enhanced = enhanced[1:-1]

        if style_suffix:
            enhanced = f"{enhanced}, {style_suffix}"

        return enhanced


class ScriptSegmenter:
    SYSTEM_PROMPT = """You are a script analyzer for video generation. Your job is to break down a script into visual segments that can be generated as individual video clips.

Rules:
- Identify distinct visual scenes based on the script
- Each segment should be 2-5 seconds of video
- Extract visual descriptions from bracketed annotations like [Show a sunset]
- For narration without visuals, create appropriate visual descriptions
- Keep segment descriptions concise and visual-focused
- Output as a JSON array of objects with "duration" (seconds) and "visual" (description) fields

Output only valid JSON, nothing else."""

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    async def close(self) -> None:
        await self.llm.close()

    async def segment(
        self,
        script: str,
        style: str = "realistic",
        total_duration: float | None = None,
    ) -> list[dict[str, Any]]:
        import json

        user_prompt = f"Analyze this script and break it into visual segments"
        if total_duration:
            user_prompt += f" (target total duration: {total_duration} seconds)"
        user_prompt += f":\n\n{script}"

        response = await self.llm.generate(
            prompt=user_prompt,
            system=self.SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.5,
        )

        try:
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                segments = json.loads(json_str)

                style_suffix = PromptEnhancer.STYLE_PROMPTS.get(style, "")
                for seg in segments:
                    if style_suffix:
                        seg["visual"] = f"{seg['visual']}, {style_suffix}"

                return segments
        except json.JSONDecodeError:
            pass

        return self._fallback_segment(script, total_duration or 10)

    def _fallback_segment(self, script: str, total_duration: float) -> list[dict[str, Any]]:
        import re

        annotations = re.findall(r"\[([^\]]+)\]", script)
        clean_script = re.sub(r"\[[^\]]+\]", "", script).strip()
        words = clean_script.split()

        num_segments = max(1, int(total_duration / 3))
        segment_duration = total_duration / num_segments

        segments = []
        if annotations:
            for i, annotation in enumerate(annotations[:num_segments]):
                segments.append(
                    {
                        "duration": segment_duration,
                        "visual": annotation,
                        "narration": " ".join(
                            words[
                                i * len(words) // len(annotations) : (i + 1)
                                * len(words)
                                // len(annotations)
                            ]
                        ),
                    }
                )
        else:
            words_per_segment = len(words) // num_segments if num_segments > 0 else len(words)
            for i in range(num_segments):
                start = i * words_per_segment
                end = start + words_per_segment if i < num_segments - 1 else len(words)
                narration = " ".join(words[start:end])
                segments.append(
                    {
                        "duration": segment_duration,
                        "visual": f"Visual representation of: {narration}",
                        "narration": narration,
                    }
                )

        return segments


async def enhance_prompt_for_video(
    prompt: str,
    style: str = "realistic",
    context: dict[str, Any] | None = None,
) -> str:
    enhancer = PromptEnhancer()
    try:
        additional = ""
        if context:
            additional = ", ".join(f"{k}: {v}" for k, v in context.items())
        return await enhancer.enhance(prompt, style, additional)
    finally:
        await enhancer.close()


async def segment_script_for_video(
    script: str,
    style: str = "realistic",
    total_duration: float | None = None,
) -> list[dict[str, Any]]:
    segmenter = ScriptSegmenter()
    try:
        return await segmenter.segment(script, style, total_duration)
    finally:
        await segmenter.close()
