import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.services.llm_service import LLMChunk, LLMClient, LLMError


class FakeStreamResponse:
    def __init__(self, events: list[dict[str, Any]], status_error: Exception | None = None):
        self.events = events
        self.status_error = status_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        if self.status_error:
            raise self.status_error

    async def aiter_lines(self) -> AsyncIterator[str]:
        for event in self.events:
            yield json.dumps(event)


class FakeStreamingClient:
    def __init__(self, events: list[dict[str, Any]]):
        self.events = events
        self.requests: list[dict[str, Any]] = []

    def stream(self, method: str, url: str, json: dict[str, Any]):
        self.requests.append({"method": method, "url": url, "json": json})
        return FakeStreamResponse(self.events)


async def collect_chunks(service: LLMClient) -> list[LLMChunk]:
    return [chunk async for chunk in service.chat_stream([{"role": "user", "content": "Hi"}])]


@pytest.mark.asyncio
async def test_chat_stream_yields_text_usage_and_done_chunks():
    client = FakeStreamingClient(
        [
            {"message": {"content": "Hel"}, "done": False},
            {"message": {"content": "lo"}, "done": False},
            {"message": {}, "done": True, "prompt_eval_count": 4, "eval_count": 2},
        ]
    )
    service = LLMClient(base_url="http://ollama.test", model="qwen3.6:35b")
    service.client = client  # type: ignore[assignment]

    chunks = await collect_chunks(service)

    assert chunks == [
        LLMChunk(type="text", content="Hel"),
        LLMChunk(type="text", content="lo"),
        LLMChunk(type="usage", tokens_in=4, tokens_out=2),
        LLMChunk(type="done"),
    ]
    assert client.requests[0]["method"] == "POST"
    assert client.requests[0]["url"] == "http://ollama.test/api/chat"
    assert client.requests[0]["json"] == {
        "model": "qwen3.6:35b",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True,
    }


@pytest.mark.asyncio
async def test_chat_stream_accumulates_tool_call_deltas_into_single_chunk():
    tool_schema = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    client = FakeStreamingClient(
        [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "get_weather", "arguments": '{"city"'}}
                    ]
                },
                "done": False,
            },
            {
                "message": {"tool_calls": [{"function": {"arguments": ': "Paris"}'}}]},
                "done": False,
            },
            {"message": {}, "done": True},
        ]
    )
    service = LLMClient(base_url="http://ollama.test", model="qwen3.6:35b")
    service.client = client  # type: ignore[assignment]

    chunks = [
        chunk
        async for chunk in service.chat_stream(
            [{"role": "user", "content": "Weather?"}],
            tools=tool_schema,
        )
    ]

    assert chunks == [
        LLMChunk(
            type="tool_call",
            tool_calls=[
                {
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Paris"}',
                    }
                }
            ],
        ),
        LLMChunk(type="done"),
    ]
    assert client.requests[0]["json"]["tools"] == tool_schema


@pytest.mark.asyncio
async def test_chat_stream_preserves_image_input_for_vision_models():
    image_message = {
        "role": "user",
        "content": "Describe this image",
        "images": ["base64-image-data"],
    }
    client = FakeStreamingClient(
        [
            {"message": {"content": "A frame"}, "done": False},
            {"message": {}, "done": True},
        ]
    )
    service = LLMClient(base_url="http://ollama.test", model="llava:latest")
    service.client = client  # type: ignore[assignment]

    chunks = [chunk async for chunk in service.chat_stream([image_message])]

    assert chunks == [LLMChunk(type="text", content="A frame"), LLMChunk(type="done")]
    assert client.requests[0]["json"]["model"] == "llava:latest"
    assert client.requests[0]["json"]["messages"] == [image_message]


@pytest.mark.asyncio
async def test_chat_stream_raises_llm_error_on_mid_stream_error():
    client = FakeStreamingClient(
        [
            {"message": {"content": "partial"}, "done": False},
            {"error": "model runner crashed", "done": True},
        ]
    )
    service = LLMClient(base_url="http://ollama.test", model="qwen3.6:35b")
    service.client = client  # type: ignore[assignment]

    stream = service.chat_stream([{"role": "user", "content": "Hi"}])
    first = await anext(stream)

    assert first == LLMChunk(type="text", content="partial")
    with pytest.raises(LLMError, match="model runner crashed"):
        await anext(stream)
