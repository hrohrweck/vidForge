import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.config import get_settings
from app.database import ErrorOrigin, ErrorSeverity

logger = logging.getLogger(__name__)


settings = get_settings()


class LLMError(Exception):
    pass


@dataclass
class LLMChunk:
    type: Literal["text", "tool_call", "usage", "done"]
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


async def resolve_llm(model_id: str, db=None) -> "LLMClient | Any":
    """Resolve a model_id to an LLM provider instance via the provider registry.

    Looks up the model in model_configs to determine the provider,
    creates an initialized instance via the registry, and verifies
    it implements the LLMProvider interface.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import ModelConfig
    from app.services.providers import registry
    from app.services.providers.base import LLMProvider

    try:
        if db is None:
            from app.workers.context import ctx

            async with ctx.session_factory() as db_session:
                return await resolve_llm(model_id, db_session)

        result = await db.execute(
            select(ModelConfig)
            .options(selectinload(ModelConfig.provider))
            .where(
                ModelConfig.model_id == model_id,
                ModelConfig.is_active == True,  # noqa: E712
            )
        )
        config = result.scalar_one_or_none()
        if config and config.provider:
            provider = config.provider
            instance = await registry.create(
                provider.provider_type, provider.id, provider.config
            )
            if not isinstance(instance, LLMProvider):
                raise LLMError(
                    f"Provider '{provider.provider_type}' does not support LLM operations"
                )
            return instance
    except LLMError:
        raise
    except Exception:
        logger.debug("Failed to resolve LLM via model_configs", exc_info=True)

    # Fall back to default Ollama client for backward compatibility
    return LLMClient()


class LLMClient:
    """Legacy backward-compatible Ollama client wrapper.

    For new code, use ``OllamaProvider`` via the provider registry.
    This class is retained for existing callers that depend on its
    convenience methods (``generate()``, ``generate_with_context()``,
    ``chat_stream()`` with tool-call merging).
    """

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = base_url or settings.ollama_url
        self.model = model or settings.llm_model or "qwen3.6:35b"
        self.client = httpx.AsyncClient(timeout=settings.llm_timeout_seconds)

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _convert_messages_for_ollama(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI vision format to Ollama's native format.

        OpenAI format: content=[{"type":"text",...}, {"type":"image_url",...}]
        Ollama format: content="text", images=["base64string"]
        """
        converted: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                text_parts: list[str] = []
                images: list[str] = []
                for part in content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            # Extract base64 from data URL
                            b64 = url.split(",", 1)[-1] if "," in url else url
                            images.append(b64)
                        else:
                            # For HTTP URLs, we'd need to download, but base64 is expected
                            text_parts.append(f"[Image: {url}]")
                new_msg = dict(msg)
                new_msg["content"] = "\n".join(text_parts)
                if images:
                    new_msg["images"] = images
                converted.append(new_msg)
            else:
                converted.append(msg)
        return converted

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Stream Ollama chat responses as typed chunks.

        Ollama's native ``/api/chat`` endpoint returns newline-delimited JSON when
        ``stream`` is true. Text is yielded immediately; tool-call fragments are
        accumulated and emitted once as a complete tool-call chunk before usage
        and done chunks.
        """

        ollama_messages = self._convert_messages_for_ollama(messages)
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": ollama_messages,
            "stream": True,
        }
        if tools is not None:
            payload["tools"] = tools

        tool_calls: list[dict[str, Any]] = []
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LLMError(f"Invalid streamed LLM response: {line}") from exc

                    if data.get("error"):
                        raise LLMError(str(data["error"]))

                    message = data.get("message") or {}
                    content = message.get("content")
                    if content:
                        yield LLMChunk(type="text", content=content)

                    incoming_tool_calls = message.get("tool_calls")
                    if incoming_tool_calls:
                        self._merge_tool_call_deltas(tool_calls, incoming_tool_calls)

                    if data.get("done"):
                        if tool_calls:
                            yield LLMChunk(type="tool_call", tool_calls=tool_calls)

                        tokens_in = data.get("prompt_eval_count")
                        tokens_out = data.get("eval_count")
                        if tokens_in is not None or tokens_out is not None:
                            yield LLMChunk(
                                type="usage",
                                tokens_in=tokens_in,
                                tokens_out=tokens_out,
                            )

                        yield LLMChunk(type="done")
                        return
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"LLM stream failed: {type(exc).__name__}: {exc}") from exc

        raise LLMError("LLM stream ended without a done chunk")

    @staticmethod
    def _merge_tool_call_deltas(
        accumulated: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> None:
        for position, tool_call in enumerate(incoming):
            index = tool_call.get("index", position) if isinstance(tool_call, dict) else position
            if not isinstance(index, int):
                index = position

            while len(accumulated) <= index:
                accumulated.append({})

            LLMClient._merge_tool_call_delta(accumulated[index], tool_call)

    @staticmethod
    def _merge_tool_call_delta(target: dict[str, Any], delta: dict[str, Any]) -> None:
        for key, value in delta.items():
            if key == "index" or value is None:
                continue

            existing = target.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                LLMClient._merge_tool_call_delta(existing, value)
            elif isinstance(existing, str) and isinstance(value, str):
                if key in {"arguments", "content"}:
                    target[key] = existing + value
                elif value and value != existing:
                    target[key] = value
            else:
                target[key] = value

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        retries: int = 3,
        provider: Any | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        if provider is not None:
            return await self._generate_with_provider(
                messages, provider, max_tokens, temperature, retries
            )

        for attempt in range(retries):
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
                content = data.get("message", {}).get("content", "")

                if not content:
                    thinking = data.get("message", {}).get("think", "") or data.get(
                        "message", {}
                    ).get("thinking", "")
                    if thinking:
                        content = thinking

                if not content:
                    raise LLMError(f"Empty response from LLM (model: {self.model})")

                import re

                clean = re.sub(r" <think>.*?</think>", "", content, flags=re.DOTALL).strip()
                clean = re.sub(r"【thinking】.*?【/thinking】", "", clean, flags=re.DOTALL).strip()
                if clean:
                    content = clean

                return content
            except Exception as e:
                wait = 2**attempt
                logger.warning(
                    "LLM request attempt %d/%d failed (wait=%ds): %s: %s",
                    attempt + 1,
                    retries,
                    wait,
                    type(e).__name__,
                    e,
                )
                if attempt < retries - 1:
                    await asyncio.sleep(wait)
                continue

    async def _generate_with_provider(
        self,
        messages: list[dict[str, Any]],
        provider: Any,
        max_tokens: int,
        temperature: float,
        retries: int,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                parts: list[str] = []
                stream = provider.chat_stream(
                    messages,
                    model=self.model,
                )
                async for chunk in stream:
                    if chunk.type == "text" and chunk.content:
                        parts.append(chunk.content)
                    if chunk.type == "done":
                        break

                content = "".join(parts)
                if not content:
                    raise LLMError("Empty response from LLM provider")

                import re

                clean = re.sub(r" <think>.*?</think>", "", content, flags=re.DOTALL).strip()
                clean = re.sub(r"【thinking】.*?【/thinking】", "", clean, flags=re.DOTALL).strip()
                if clean:
                    content = clean

                return content
            except Exception as e:
                last_error = e
                wait = 2**attempt
                logger.warning(
                    "LLM provider request attempt %d/%d failed (wait=%ds): %s: %s",
                    attempt + 1,
                    retries,
                    wait,
                    type(e).__name__,
                    e,
                )
                if attempt < retries - 1:
                    await asyncio.sleep(wait)
                continue

        error_type = type(last_error).__name__ if last_error else "Unknown"
        error_msg = str(last_error) if last_error else "no error details"
        raise LLMError(
            f"LLM provider request failed after {retries} attempts: {error_type}: {error_msg}"
        )

        error_type = type(last_error).__name__ if last_error else "Unknown"
        error_msg = str(last_error) if last_error else "no error details"
        full_error = f"{error_type}: {error_msg}"
        # Capture error for notification system (best-effort, no Job context here)
        try:
            from app.services.error_capture import log_system_error
            from app.workers.context import ctx

            async with ctx.session_factory() as error_db:
                await log_system_error(
                    error_db,
                    severity=ErrorSeverity.ERROR,
                    origin=ErrorOrigin.LLM,
                    message="AI assistant is unavailable, please try again later",
                    details={
                        "exception_type": error_type,
                        "exception_message": error_msg,
                        "retry_count": retries,
                        "model": self.model,
                    },
                )
        except Exception:
            logger.debug("Failed to capture LLM error for notification", exc_info=True)

        raise LLMError(f"LLM request failed after {retries} attempts: {full_error}")

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

    def __init__(self, llm_client: LLMClient | None = None, provider: Any | None = None, model: str | None = None):
        self.llm = llm_client or LLMClient(model=model)
        self.provider = provider

    async def close(self) -> None:
        await self.llm.close()
        if self.provider is not None and hasattr(self.provider, "shutdown"):
            await self.provider.shutdown()

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
            provider=self.provider,
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

        user_prompt = "Analyze this script and break it into visual segments"
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
