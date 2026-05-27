"""AtlasCloud.ai provider — OpenAI-compatible LLM + custom image/video API."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx

from app.services.llm_service import LLMChunk, LLMError
from app.services.providers.base import ComfyUIProvider, JobResult, ProviderInfo

logger = logging.getLogger(__name__)

ATLAS_LLM_BASE = "https://api.atlascloud.ai/v1"
ATLAS_API_BASE = "https://api.atlascloud.ai/api/v1"


class AtlasCloudProvider(ComfyUIProvider):
    """AtlasCloud.ai provider.

    LLM: OpenAI-compatible streaming via /v1/chat/completions.
    Image/Video: asynchronous generation via /model/generateImage /
    /model/generateVideo with /model/getResult polling.
    """

    _models_without_tools: set[str] = set()

    def __init__(self, provider_id: UUID, config: dict) -> None:
        self.provider_id = provider_id
        self.api_key = config.get("api_key", "")
        self.base_url = ATLAS_LLM_BASE
        self.client: httpx.AsyncClient | None = None

    # ── Initialization ────────────────────────────────────────────

    async def initialize(self, config: dict) -> None:
        if not config.get("api_key"):
            raise ValueError("api_key is required for AtlasCloud provider")
        self.api_key = config["api_key"]
        self.client = httpx.AsyncClient(timeout=300.0)

    # ── ComfyUI abstract methods (not used — no ComfyUI workflows) ─

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        raise NotImplementedError("AtlasCloud uses direct API calls, not ComfyUI")

    async def wait_for_completion(self, job_id: str) -> dict:
        raise NotImplementedError("Use generate_image/generate_video instead")

    async def get_output(self, result: dict) -> bytes | None:
        raise NotImplementedError("Use generate_image/generate_video instead")

    async def cancel_job(self, job_id: str) -> bool:
        return False  # AtlasCloud doesn't support cancellation via our patterns

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(
            name="AtlasCloud",
            provider_type="atlascloud",
            is_available=self.client is not None,
            message="Connected" if self.client else "Not initialized",
        )

    async def shutdown(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    # ── LLM Chat (OpenAI-compatible — same as Poe) ─────────────────

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        client = self.client
        if not client:
            raise RuntimeError("Provider not initialized")

        effective_tools = tools
        if effective_tools and model in self._models_without_tools:
            effective_tools = None

        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if effective_tools:
            payload["tools"] = effective_tools

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
                    if effective_tools and "does not support tool calling" in body_text:
                        self._models_without_tools.add(model)
                        logger.warning("Model %s does not support tools, retrying", model)
                        payload.pop("tools", None)
                        async with client.stream(
                            "POST",
                            f"{self.base_url}/chat/completions",
                            json=payload,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                        ) as retry_response:
                            if retry_response.status_code != 200:
                                rb = await retry_response.aread()
                                raise LLMError(
                                    f"AtlasCloud API error ({retry_response.status_code}): "
                                    f"{rb.decode('utf-8', errors='replace')[:500]}"
                                )
                            async for event in self._stream_events(retry_response):
                                yield event
                            return
                    raise LLMError(
                        f"AtlasCloud API error ({response.status_code}): {body_text[:500]}"
                    )
                async for event in self._stream_events(response):
                    yield event
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"AtlasCloud stream failed: {type(exc).__name__}: {exc}") from exc

        yield LLMChunk(type="done")

    # ── Streaming helpers ─────────────────────────────────────────

    async def _stream_events(self, response: httpx.Response) -> AsyncIterator[LLMChunk]:
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None

        async for line in response.aiter_lines():
            if not line:
                continue

            data = self._parse_sse_line(line)
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
                msg = error.get("message") if isinstance(error, dict) else str(error)
                raise LLMError(msg)

            if data.get("usage"):
                usage = data["usage"]

            choices = data.get("choices") or []
            if not choices:
                continue

            delta = choices[0].get("delta") or {}

            reasoning = delta.get("reasoning_content")
            if reasoning:
                yield LLMChunk(type="text", content=f"<think>{reasoning}</think>")

            content = delta.get("content")
            if content:
                yield LLMChunk(type="text", content=content)

            incoming = delta.get("tool_calls")
            if incoming:
                self._merge_tool_call_deltas(tool_calls, incoming)

    @staticmethod
    def _parse_sse_line(line: str) -> dict[str, Any] | None:
        data = line.strip()
        if data.startswith("data:"):
            data = data.removeprefix("data:").strip()
        if data == "[DONE]":
            return None
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise LLMError(f"Invalid SSE: {line}")
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _merge_tool_call_deltas(
        accumulated: list[dict[str, Any]], incoming: list[dict[str, Any]]
    ) -> None:
        for pos, tc in enumerate(incoming):
            idx = tc.get("index", pos) if isinstance(tc, dict) else pos
            if not isinstance(idx, int):
                idx = pos
            while len(accumulated) <= idx:
                accumulated.append({})
            AtlasCloudProvider._merge_one(accumulated[idx], tc)

    @staticmethod
    def _merge_one(target: dict[str, Any], delta: dict[str, Any]) -> None:
        for key, value in delta.items():
            if key == "index" or value is None:
                continue
            existing = target.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                AtlasCloudProvider._merge_one(existing, value)
            elif isinstance(existing, str) and isinstance(value, str):
                if key in {"arguments", "content"}:
                    target[key] = existing + value
                elif value and value != existing:
                    target[key] = value
            else:
                target[key] = value

    # ── Image Generation (AtlasCloud async API) ───────────────────

    async def generate_image(
        self,
        prompt: str,
        model: str = "flux-1.1-pro",
        aspect_ratio: str = "3:2",
        size: str | None = None,
        negative_prompt: str | None = None,
    ) -> tuple[str, bytes] | None:
        """Submit an image generation job and poll until completion."""
        client = self.client
        if not client:
            raise RuntimeError("Provider not initialized")

        payload: dict[str, Any] = {"model": model, "prompt": [prompt]}
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        # Submit
        resp = await client.post(
            f"{ATLAS_API_BASE}/model/generateImage",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        if resp.status_code != 200:
            body = await resp.aread()
            raise LLMError(
                f"AtlasCloud image error ({resp.status_code}): "
                f"{body.decode('utf-8', errors='replace')[:500]}"
            )

        data = resp.json()
        # AtlasCloud wraps in {code, data: {id, urls: {get}}}
        inner = data.get("data", data)
        prediction_id = inner.get("id") or data.get("predictionId")
        poll_url = (inner.get("urls", {}).get("get") or
                    f"{ATLAS_API_BASE}/model/getResult")
        if not prediction_id:
            raise LLMError(f"No prediction ID in response: {data}")

        # Poll for result
        for _ in range(120):  # 4 minutes max
            await asyncio.sleep(2)
            poll = await client.get(
                poll_url if "http" in (poll_url or "") else f"{ATLAS_API_BASE}/model/getResult",
                params={"predictionId": prediction_id} if "http" not in (poll_url or "") else None,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if poll.status_code != 200:
                try:
                    err_body = poll.json()
                    err_msg = (
                        err_body.get("message")
                        or err_body.get("msg", "")
                    )
                    # Check nested data for more detail
                    err_data = err_body.get("data", {})
                    if isinstance(err_data, dict):
                        err_msg = err_data.get("message", "") or err_msg
                    # Also check the raw body for embedded errors
                    raw = str(err_body)
                    if "api node returned 400" in raw.lower():
                        err_msg = "Model not available or unsupported parameters"
                    if err_msg:
                        raise LLMError(f"AtlasCloud error: {err_msg}")
                    # If no message found, include raw body for debugging
                    raise LLMError(f"AtlasCloud returned {poll.status_code}: {raw[:200]}")
                except LLMError:
                    raise
                except Exception:
                    pass
                continue

            result = poll.json()
            inner_result = result.get("data", result)
            status = inner_result.get("status", "") or result.get("status", "")
            if status == "completed":
                outputs = inner_result.get("outputs") or inner_result.get("output")
                image_url = (inner_result.get("url")
                             or (outputs.get("image") if isinstance(outputs, dict) else None)
                             or (outputs[0] if isinstance(outputs, list) and outputs else None)
                             or result.get("image_url", "")
                             or result.get("output", ""))
                if image_url:
                    img_resp = await client.get(image_url)
                    img_resp.raise_for_status()
                    return model, img_resp.content
                raise LLMError(f"No image URL in completed result: {result}")
            if status == "failed":
                err = inner_result.get("error", "") or result.get("error", "Unknown error")
                raise LLMError(f"Image generation failed: {err}")

        raise LLMError("Image generation timed out")

    # ── Video Generation (AtlasCloud async API) ───────────────────

    async def generate_video(
        self,
        prompt: str,
        model: str = "kling-v2.0",
        duration: int | None = None,
        aspect_ratio: str = "16:9",
        image_path: str | None = None,
        reference_image_url: str | None = None,
    ) -> tuple[str, bytes] | None:
        """Submit a video generation job and poll until completion."""
        client = self.client
        if not client:
            raise RuntimeError("Provider not initialized")

        ref_url = image_path or reference_image_url
        payload: dict[str, Any] = {"model": model, "prompt": [prompt]}
        # Only include image_url if it looks like an actual URL (not a local path)
        if ref_url and (ref_url.startswith("http://") or ref_url.startswith("https://")):
            payload["image_url"] = ref_url

        logger.warning(f"AtlasCloud video payload: {json.dumps(payload)[:500]}")

        resp = await client.post(
            f"{ATLAS_API_BASE}/model/generateVideo",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        if resp.status_code != 200:
            body = await resp.aread()
            raise LLMError(
                f"AtlasCloud video error ({resp.status_code}): "
                f"{body.decode('utf-8', errors='replace')[:500]}"
            )

        data = resp.json()
        # AtlasCloud wraps in {code, data: {id, urls: {get}}}}
        inner = data.get("data", data)
        prediction_id = inner.get("id") or data.get("predictionId")
        poll_url = (inner.get("urls", {}).get("get") or
                    f"{ATLAS_API_BASE}/model/getResult")
        if not prediction_id:
            raise LLMError(f"No prediction ID in response: {data}")

        for _ in range(300):  # 10 minutes max
            await asyncio.sleep(2)
            poll = await client.get(
                poll_url if "http" in (poll_url or "") else f"{ATLAS_API_BASE}/model/getResult",
                params={"predictionId": prediction_id} if "http" not in (poll_url or "") else None,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if poll.status_code != 200:
                try:
                    err_body = poll.json()
                    err_msg = err_body.get("message") or err_body.get("msg", "")
                    # Check nested data for error too
                    err_data = err_body.get("data", {})
                    if isinstance(err_data, dict):
                        err_msg = err_data.get("message", "") or err_msg
                    if err_msg:
                        raise LLMError(f"AtlasCloud error: {err_msg}")
                except LLMError:
                    raise
                except Exception:
                    pass
                continue

            result = poll.json()
            inner_result = result.get("data", result)
            status = inner_result.get("status", "") or result.get("status", "")
            if status == "completed":
                outputs = inner_result.get("outputs") or inner_result.get("output")
                video_url = (inner_result.get("url") or
                             (outputs.get("video") if isinstance(outputs, dict) else None) or
                             (outputs[0] if isinstance(outputs, list) and outputs else None))
                if not video_url:
                    video_url = result.get("video_url", "") or result.get("output", "")
                    if isinstance(video_url, dict):
                        video_url = video_url.get("video") or video_url.get("url", "")
                if video_url:
                    vid_resp = await client.get(video_url)
                    vid_resp.raise_for_status()
                    return model, vid_resp.content
                raise LLMError(f"No video URL in completed result: {result}")
            if status == "failed":
                err = inner_result.get("error", "") or result.get("error", "Unknown error")
                raise LLMError(f"Video generation failed: {err}")

        raise LLMError("Video generation timed out")

    def estimate_cost(self, workflow: dict[str, Any]) -> float:
        return 0.0

    def estimate_duration(self, workflow: dict[str, Any]) -> float:
        return 60.0


async def create_atlascloud_provider(provider_id: UUID, config: dict) -> AtlasCloudProvider:
    instance = AtlasCloudProvider(provider_id, config)
    await instance.initialize(config)
    return instance
