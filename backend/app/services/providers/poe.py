import asyncio
import base64
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, Awaitable, Callable
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

from app.services.llm_service import LLMChunk, LLMError
from app.services.providers.base import ComfyUIProvider, ProviderInfo


class PoeProvider(ComfyUIProvider):
    _models_without_tools: set[str] = set()  # Cache of models that don't support tool calling

    _TOOL_CAPABLE_TEXT_MODELS = {
        "claude-opus-4.7",
        "claude-sonnet-4.6",
        "gemini-3.1-pro",
        "gpt-5.4",
        "o3-mini",
        "glm-5.1-t",
    }

    _POE_TEXT_MODELS = (
        "claude",
        "gemini",
        "gpt",
        "o1",
        "o3",
        "o4",
        "qwen",
        "glm",
    )

    def __init__(self, provider_id: UUID, config: dict):
        self.provider_id = provider_id
        self.config = config
        self.api_key = config.get("api_key", "")
        self.base_url = "https://api.poe.com/v1"
        self.client: httpx.AsyncClient | None = None
        self._max_concurrent = config.get("max_concurrent_jobs", 1)
        self._current_jobs = 0
        self._available_models: list[dict] = []
        self._model_cache: dict[str, dict] = {}

    async def initialize(self, config: dict) -> None:
        if not config.get("api_key"):
            raise ValueError("api_key is required for Poe provider")
        self.api_key = config["api_key"]
        self.client = httpx.AsyncClient(timeout=300.0)
        await self._discover_models()

    async def _discover_models(self) -> None:
        if not self.client:
            return

        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                self._available_models = data.get("data", [])
                self._model_cache = {
                    m["id"]: m for m in self._available_models
                }
        except Exception:
            pass

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        raise NotImplementedError("Poe provider uses different method for media generation")

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Stream Poe chat completions as the shared LLMChunk contract."""
        client = self.client
        if not client:
            raise RuntimeError("Provider not initialized")

        # Skip tools if we know this model doesn't support them
        effective_tools = tools
        if effective_tools and model in self._models_without_tools:
            effective_tools = None

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if effective_tools:
            payload["tools"] = effective_tools

        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None

        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    body_text = body.decode("utf-8", errors="replace")
                    # Auto-detect models that don't support tool calling
                    if (
                        effective_tools
                        and "does not support tool calling" in body_text
                    ):
                        self._models_without_tools.add(model)
                        # Retry without tools
                        logger.warning(
                            "Model %s does not support tools, retrying without",
                            model,
                        )
                        payload.pop("tools", None)
                        # Re-send the request without tools
                        async with client.stream(
                            "POST",
                            f"{self.base_url}/chat/completions",
                            json=payload,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                        ) as retry_response:
                            if retry_response.status_code != 200:
                                retry_body = await retry_response.aread()
                                raise LLMError(
                                    f"Poe API error ({retry_response.status_code}): "
                                    f"{retry_body.decode('utf-8', errors='replace')[:500]}"
                                )
                            async for event in self._stream_events(retry_response):
                                yield event
                            return
                    raise LLMError(
                        f"Poe API error ({response.status_code}): "
                        f"{body_text[:500]}"
                    )
                async for event in self._stream_events(response):
                    yield event
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Poe stream failed: {type(exc).__name__}: {exc}") from exc

        raise LLMError("Poe stream ended without a done chunk")

    async def _stream_events(
        self,
        response: httpx.Response,
    ) -> AsyncIterator[LLMChunk]:
        """Yield LLMChunks from an open SSE response stream."""
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None

        async for line in response.aiter_lines():
            if not line:
                continue

            data = self._parse_stream_line(line)
            if data is None:
                if tool_calls:
                    yield LLMChunk(type="tool_call", tool_calls=tool_calls)
                if usage:
                    yield LLMChunk(
                        type="usage",
                        tokens_in=usage.get("prompt_tokens"),
                        tokens_out=usage.get("completion_tokens"),
                    )
                yield LLMChunk(type="done")
                return

            if error := data.get("error"):
                if isinstance(error, dict):
                    raise LLMError(str(error.get("message") or error))
                raise LLMError(str(error))

            if data.get("usage"):
                usage = data["usage"]

            choices = data.get("choices") or []
            if not choices:
                continue

            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            reasoning = delta.get("reasoning_content")

            # DEBUG: log the delta keys to see what Poe returns
            delta_keys = [k for k, v in delta.items() if v]
            if delta_keys:
                logger.info(
                    "[Poe delta] keys=%s content_len=%d reasoning=%s",
                    delta_keys,
                    len(content or ""),
                    bool(reasoning),
                )

            if reasoning:
                # Wrap reasoning in <think> tags so the frontend can parse it
                yield LLMChunk(type="text", content=f"<think>{reasoning}</think>")
            if content:
                yield LLMChunk(type="text", content=content)

            incoming_tool_calls = delta.get("tool_calls")
            if incoming_tool_calls:
                self._merge_tool_call_deltas(tool_calls, incoming_tool_calls)

    @staticmethod
    def _parse_stream_line(line: str) -> dict[str, Any] | None:
        data = line.strip()
        if data.startswith("data:"):
            data = data.removeprefix("data:").strip()
        if data == "[DONE]":
            return None
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Invalid streamed Poe response: {line}") from exc
        if not isinstance(parsed, dict):
            raise LLMError(f"Invalid streamed Poe response: {line}")
        return parsed

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

            PoeProvider._merge_tool_call_delta(accumulated[index], tool_call)

    @staticmethod
    def _merge_tool_call_delta(target: dict[str, Any], delta: dict[str, Any]) -> None:
        for key, value in delta.items():
            if key == "index" or value is None:
                continue

            existing = target.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                PoeProvider._merge_tool_call_delta(existing, value)
            elif isinstance(existing, str) and isinstance(value, str):
                if key in {"arguments", "content"}:
                    target[key] = existing + value
                elif value and value != existing:
                    target[key] = value
            else:
                target[key] = value

    # Aspect ratio to size mapping for Poe Videos API
    _ASPECT_RATIO_SIZES: dict[str, str] = {
        "16:9": "1920x1080",
        "9:16": "1080x1920",
        "1:1": "1080x1080",
        "4:3": "1440x1080",
        "3:4": "1080x1440",
        "3:2": "1440x960",
        "2:3": "960x1440",
    }

    # Models that use the /v1/videos (async polling) API
    _VIDEO_API_MODELS = {
        "veo-3.1", "veo-3.1-fast", "veo-3", "veo-2", "veo-2-video",
        "veo-v3.1", "veo-v3.1-fast", "veo-3-vfast", "veo-3-fast",
    }

    def _is_video_api_model(self, model: str) -> bool:
        """True if the model uses /v1/videos; False means chat-completions style."""
        return model.lower() in self._VIDEO_API_MODELS

    async def generate_video(
        self,
        prompt: str,
        model: str = "Veo-3",
        duration: int = 10,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        negative_prompt: str = "",
        image_path: str | None = None,
    ) -> tuple[str, bytes | None]:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        if self._is_video_api_model(model):
            return await self._generate_video_api(
                prompt, model, duration, aspect_ratio, image_path,
            )
        else:
            return await self._generate_video_chat(
                prompt, model, duration, aspect_ratio, image_path,
            )

    async def _generate_video_chat(
        self,
        prompt: str,
        model: str,
        duration: int,
        aspect_ratio: str,
        image_path: str | None,
    ) -> tuple[str, bytes | None]:
        """Generate video via /v1/chat/completions (wan, sora, hunyuan, etc.)."""
        import logging
        logger = logging.getLogger(__name__)

        # Build message content — optional reference image
        content: list[dict[str, Any]] | str
        if image_path:
            from pathlib import Path

            from app.config import get_settings
            settings = get_settings()
            full_image_path = Path(settings.storage_path) / image_path
            if full_image_path.exists():
                image_bytes = full_image_path.read_bytes()
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                content = [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ]
            else:
                content = prompt
        else:
            content = prompt

        logger.info(
            f"Poe generate_video (chat): model={model}, has_image={image_path is not None}"
        )

        client = self.client
        if not client:
            raise RuntimeError("Provider not initialized")

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "stream": False,
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

        if response.status_code != 200:
            raise RuntimeError(f"Poe chat video error ({response.status_code}): {response.text[:300]}")

        result = response.json()
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        video_bytes = self._parse_media_content(text)
        if not video_bytes:
            raise RuntimeError(
                f"Poe chat video returned no data (model={model}, text={text[:200]})"
            )

        logger.info(f"Poe video (chat): downloaded {len(video_bytes)} bytes")
        return result.get("id", ""), video_bytes

    async def _generate_video_api(
        self,
        prompt: str,
        model: str,
        duration: int,
        aspect_ratio: str,
        image_path: str | None,
    ) -> tuple[str, bytes | None]:
        """Generate video via /v1/videos async polling API (Veo, etc.)."""
        import logging
        logger = logging.getLogger(__name__)

        size = self._ASPECT_RATIO_SIZES.get(aspect_ratio, "1920x1080")

        create_body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "seconds": min(duration, 8),
            "size": size,
        }

        if image_path:
            from pathlib import Path

            from app.config import get_settings
            settings = get_settings()
            full_image_path = Path(settings.storage_path) / image_path
            if full_image_path.exists():
                image_bytes = full_image_path.read_bytes()
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                create_body["input_image"] = f"data:image/png;base64,{image_b64}"

        logger.info(
            f"Poe generate_video (api): model={model}, size={size}, "
            f"seconds={create_body['seconds']}, has_image={'input_image' in create_body}"
        )

        client = self.client
        if not client:
            raise RuntimeError("Provider not initialized")

        # Step 1: Create video
        create_response = await client.post(
            f"{self.base_url}/videos",
            json=create_body,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

        if create_response.status_code not in (200, 201):
            error_msg = create_response.text
            raise RuntimeError(f"Poe Videos API create error: {error_msg}")

        video_data = create_response.json()
        video_id = video_data.get("id", "")
        status = video_data.get("status", "queued")

        logger.info(f"Poe video created: id={video_id}, status={status}")

        # Step 2: Poll until completed
        poll_interval = 5.0
        timeout = 300.0
        elapsed = 0.0

        while status in ("queued", "in_progress") and elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_response = await client.get(
                f"{self.base_url}/videos/{video_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

            if poll_response.status_code != 200:
                raise RuntimeError(f"Poe Videos API poll error: {poll_response.text}")

            video_data = poll_response.json()
            status = video_data.get("status", "failed")
            progress = video_data.get("progress", 0)
            logger.info(f"Poe video poll: id={video_id}, status={status}, progress={progress}")

        if status == "failed":
            error = video_data.get("error", {})
            raise RuntimeError(f"Poe video generation failed: {error}")

        if status != "completed":
            raise RuntimeError(f"Poe video generation timed out after {timeout}s (status={status})")

        # Step 3: Download video content
        download_response = await client.get(
            f"{self.base_url}/videos/{video_id}/content",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

        if download_response.status_code != 200:
            raise RuntimeError(f"Poe Videos API download error: {download_response.text}")

        video_bytes = download_response.content
        logger.info(f"Poe video downloaded: id={video_id}, size={len(video_bytes)} bytes")

        return video_id, video_bytes

        return video_id, video_bytes

    async def generate_image(
        self,
        prompt: str,
        model: str = "GPT-Image-1",
        aspect_ratio: str = "3:2",
        quality: str = "high",
        negative_prompt: str = "",
        image_path: str | None = None,
    ) -> tuple[str, bytes | None]:
        if not self.client:
            raise RuntimeError("Provider not initialized")

        # Build message content with optional image (OpenAI vision format)
        content: list[dict[str, Any]] | str
        if image_path:
            from pathlib import Path

            from app.config import get_settings
            settings = get_settings()
            full_image_path = Path(settings.storage_path) / image_path
            if full_image_path.exists():
                image_bytes = full_image_path.read_bytes()
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        },
                    },
                    {"type": "text", "text": prompt},
                ]
            else:
                content = prompt
        else:
            content = prompt
        messages = [{"role": "user", "content": content}]
        if negative_prompt:
            messages.append({"role": "user", "content": f"Negative: {negative_prompt}"})

        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Poe generate_image request: model={model}, has_image={image_path is not None}")

        client = self.client
        if not client:
            raise RuntimeError("Provider not initialized")

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

        if response.status_code != 200:
            error_msg = response.text
            raise RuntimeError(f"Poe API error: {error_msg}")

        result = response.json()
        content = str(result.get("choices", [{}])[0].get("message", {}).get("content", ""))

        return result.get("id", ""), self._parse_media_content(content)

    def _parse_media_content(self, content: str) -> bytes | None:
        if not content:
            return None

        # 1. Try JSON-structured response
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if "image_base64" in data:
                    return base64.b64decode(data["image_base64"])
                elif "video_base64" in data:
                    return base64.b64decode(data["video_base64"])
                elif "image_url" in data:
                    return self._sync_download(data["image_url"])
                elif "video_url" in data:
                    return self._sync_download(data["video_url"])
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Parse Markdown image syntax: ![alt](url)
        md_match = re.search(r"!\[[^\]]*\]\((https?://[^\s)]+)\)", content)
        if md_match:
            result = self._sync_download(md_match.group(1))
            if result:
                return result

        # 3. Parse bare URL (poecdn.net, etc.)
        url_pat = r'(https?://\S+\.(?:png|jpg|jpeg|webp|gif|mp4|webm))'
        url_match = re.search(url_pat, content, re.IGNORECASE)
        if not url_match:
            # Broader: any URL on a known CDN domain
            url_match = re.search(r'(https?://\S+poecdn\S+)', content)
        if not url_match:
            # Even broader: any URL that looks like a media URL
            url_match = re.search(
                r'(https?://\S+/(?:image|video|media|base)/\S+)',
                content, re.IGNORECASE,
            )
        if url_match:
            result = self._sync_download(url_match.group(1))
            if result:
                return result

        return None

    @staticmethod
    def _sync_download(url: str) -> bytes | None:
        """Download content from a URL synchronously."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "VidForge/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                logger.debug(f"Downloaded {len(data)} bytes from {url[:80]}")
                return data
        except Exception as e:
            logger.warning(f"Failed to download {url[:80]}: {e}")
            return None

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict:
        return {"status": "completed", "job_id": job_id}

    async def get_output(self, result: dict) -> bytes | None:
        return result.get("output_data")

    async def cancel_job(self, job_id: str) -> bool:
        return False

    async def get_status(self) -> ProviderInfo:
        if not self.client:
            return ProviderInfo(
                name="poe",
                provider_type="poe",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=None,
                message="Provider not initialized",
            )

        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if response.status_code == 200:
                video_models = self.get_models_by_modality("video")
                image_models = self.get_models_by_modality("image")
                return ProviderInfo(
                    name="poe",
                    provider_type="poe",
                    is_available=True,
                    estimated_wait_seconds=60,
                    cost_per_job=0.0,
                    message=f"Ready - {len(video_models)} video, {len(image_models)} image models available",
                )
        except Exception as e:
            return ProviderInfo(
                name="poe",
                provider_type="poe",
                is_available=False,
                estimated_wait_seconds=0,
                cost_per_job=None,
                message=f"Error: {str(e)}",
            )

        return ProviderInfo(
            name="poe",
            provider_type="poe",
            is_available=False,
            estimated_wait_seconds=0,
            cost_per_job=None,
            message="API key invalid or Poe service unavailable",
        )

    async def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    async def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 60.0

    async def shutdown(self) -> None:
        if self.client:
            await self.client.aclose()

    def get_models_by_modality(self, modality: str) -> list[dict]:
        return [
            m
            for m in self._available_models
            if m.get("architecture", {}).get("output_modalities", []).count(modality) > 0
        ]

    def get_video_models(self) -> list[dict]:
        return self.get_models_by_modality("video")

    def get_image_models(self) -> list[dict]:
        return self.get_models_by_modality("image")

    def get_text_models(self) -> list[dict]:
        text_only = [
            {
                **m,
                "supports_tools": self._model_supports_tools(m.get("id", "")),
            }
            for m in self._available_models
            if self._is_text_model(m)
        ]
        return text_only

    @classmethod
    def _is_text_model(cls, model: dict[str, Any]) -> bool:
        output_modalities = model.get("architecture", {}).get("output_modalities")
        if output_modalities == ["text"]:
            return True
        model_id = str(model.get("id", "")).lower()
        return any(model_id.startswith(prefix) for prefix in cls._POE_TEXT_MODELS)

    @classmethod
    def _model_supports_tools(cls, model_id: str) -> bool:
        return model_id.lower() in cls._TOOL_CAPABLE_TEXT_MODELS


async def create_poe_provider(provider_id: UUID, config: dict) -> PoeProvider:
    provider = PoeProvider(provider_id, config)
    await provider.initialize(config)
    return provider
