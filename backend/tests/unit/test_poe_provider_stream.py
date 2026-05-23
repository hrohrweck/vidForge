import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest

from app.services.llm_service import LLMChunk, LLMError
from app.services.providers.poe import PoeProvider


class FakePoeStreamResponse:
    def __init__(self, events: list[dict[str, Any] | str]):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self) -> AsyncIterator[str]:
        for event in self.events:
            if isinstance(event, str):
                yield event
            else:
                yield f"data: {json.dumps(event)}"


class FakePoeStreamingClient:
    def __init__(self, events: list[dict[str, Any] | str]):
        self.events = events
        self.requests: list[dict[str, Any]] = []

    def stream(
        self,
        method: str,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str],
    ):
        self.requests.append(
            {"method": method, "url": url, "json": json, "headers": headers}
        )
        return FakePoeStreamResponse(self.events)


def create_provider(client: FakePoeStreamingClient) -> PoeProvider:
    provider = PoeProvider(uuid4(), {"api_key": "test-token"})
    provider.client = client  # type: ignore[assignment]
    return provider


@pytest.mark.asyncio
async def test_chat_stream_yields_text_usage_and_done_chunks():
    client = FakePoeStreamingClient(
        [
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2}},
            "data: [DONE]",
        ]
    )
    provider = create_provider(client)

    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "Hi"}],
            model="GPT-5.4",
        )
    ]

    assert chunks == [
        LLMChunk(type="text", content="Hel"),
        LLMChunk(type="text", content="lo"),
        LLMChunk(type="usage", tokens_in=4, tokens_out=2),
        LLMChunk(type="done"),
    ]
    assert client.requests[0] == {
        "method": "POST",
        "url": "https://api.poe.com/v1/chat/completions",
        "json": {
            "model": "GPT-5.4",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
        "headers": {"Authorization": "Bearer test-token"},
    }


@pytest.mark.asyncio
async def test_chat_stream_accumulates_openai_tool_call_deltas():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_job",
                "description": "Create a draft job",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    client = FakePoeStreamingClient(
        [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "create_job",
                                        "arguments": '{"title"',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": ': "Demo"}'}}
                            ]
                        }
                    }
                ]
            },
            "data: [DONE]",
        ]
    )
    provider = create_provider(client)

    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "Draft a video"}],
            model="GPT-5.4",
            tools=tools,
        )
    ]

    assert chunks == [
        LLMChunk(
            type="tool_call",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "create_job",
                        "arguments": '{"title": "Demo"}',
                    },
                }
            ],
        ),
        LLMChunk(type="done"),
    ]
    assert client.requests[0]["json"]["tools"] == tools


@pytest.mark.asyncio
async def test_chat_stream_raises_llm_error_on_streamed_error():
    client = FakePoeStreamingClient(
        [
            {"choices": [{"delta": {"content": "partial"}}]},
            {"error": {"message": "rate limited"}},
        ]
    )
    provider = create_provider(client)

    stream = provider.chat_stream([{"role": "user", "content": "Hi"}], model="GPT-5.4")
    first = await anext(stream)

    assert first == LLMChunk(type="text", content="partial")
    with pytest.raises(LLMError, match="rate limited"):
        await anext(stream)


def test_get_text_models_marks_tool_support_from_allowlist():
    provider = PoeProvider(uuid4(), {"api_key": "test-token"})
    provider._available_models = [
        {"id": "GPT-5.4", "architecture": {"output_modalities": ["text"]}},
        {"id": "Some-Text-Bot", "architecture": {"output_modalities": ["text"]}},
        {"id": "Image-Bot", "architecture": {"output_modalities": ["image"]}},
    ]

    models = provider.get_text_models()

    assert models == [
        {
            "id": "GPT-5.4",
            "architecture": {"output_modalities": ["text"]},
            "supports_tools": True,
        },
        {
            "id": "Some-Text-Bot",
            "architecture": {"output_modalities": ["text"]},
            "supports_tools": False,
        },
    ]
