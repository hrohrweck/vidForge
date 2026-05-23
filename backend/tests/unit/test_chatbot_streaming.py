"""Tests for SSE streaming utilities."""

import json
from unittest.mock import AsyncMock

import pytest

from app.chatbot.streaming import (
    SSEEventType,
    encode_sse_event,
    sse_stream,
)


class TestEncodeSseEvent:
    """Tests for encode_sse_event function."""

    def test_basic_ascii(self):
        """ASCII text in data."""
        result = encode_sse_event("token", {"content": "hello"})
        assert result == b"event: token\ndata: {\"content\": \"hello\"}\n\n"

    def test_unicode_content(self):
        """Unicode characters in data."""
        result = encode_sse_event("token", {"content": "こんにちは"})
        expected = 'event: token\ndata: {"content": "こんにちは"}\n\n'
        assert result == expected.encode("utf-8")

    def test_multiline_text(self):
        """Newlines within data values."""
        result = encode_sse_event("token", {"content": "line1\nline2"})
        expected = 'event: token\ndata: {"content": "line1\\nline2"}\n\n'
        assert result == expected.encode("utf-8")

    def test_json_with_nested_newlines(self):
        """JSON containing newlines in nested structures."""
        data = {"choices": [{"delta": {"content": "line1\nline2"}}]}
        result = encode_sse_event("token", data)
        expected = (
            b"event: token\ndata: "
            + json.dumps(data).encode("utf-8")
            + b"\n\n"
        )
        assert result == expected

    def test_empty_data(self):
        """Empty dict data."""
        result = encode_sse_event("done", {})
        assert result == b"event: done\ndata: {}\n\n"

    def test_error_event_type(self):
        """Error event type."""
        result = encode_sse_event("error", {"message": "something went wrong"})
        assert result == b'event: error\ndata: {"message": "something went wrong"}\n\n'

    def test_usage_event_type(self):
        """Usage event type with numeric fields."""
        result = encode_sse_event(
            "usage",
            {"prompt_tokens": 100, "completion_tokens": 50},
        )
        assert result == b'event: usage\ndata: {"prompt_tokens": 100, "completion_tokens": 50}\n\n'

    def test_tool_call_start_event(self):
        """Tool call start event."""
        result = encode_sse_event("tool_call_start", {"name": "get_weather", "args": {}})
        assert result == b'event: tool_call_start\ndata: {"name": "get_weather", "args": {}}\n\n'

    def test_tool_call_result_event(self):
        """Tool call result event."""
        result = encode_sse_event("tool_call_result", {"name": "get_weather", "result": "sunny"})
        assert result == b'event: tool_call_result\ndata: {"name": "get_weather", "result": "sunny"}\n\n'


class TestSseStream:
    """Tests for sse_stream async helper."""

    @pytest.mark.asyncio
    async def test_single_event(self):
        """Single SSE event in stream."""
        events = AsyncMock()
        events.__aiter__ = lambda self: self

        async def generator():
            yield ("token", {"content": "hello"})

        result = [chunk async for chunk in sse_stream(generator())]
        assert len(result) == 1
        assert result[0] == b'event: token\ndata: {"content": "hello"}\n\n'

    @pytest.mark.asyncio
    async def test_multiple_events(self):
        """Multiple events streamed."""
        async def generator():
            yield ("token", {"content": "first"})
            yield ("token", {"content": "second"})

        result = [chunk async for chunk in sse_stream(generator())]
        assert len(result) == 2
        assert result[0] == b'event: token\ndata: {"content": "first"}\n\n'
        assert result[1] == b'event: token\ndata: {"content": "second"}\n\n'

    @pytest.mark.asyncio
    async def test_different_event_types(self):
        """Different event types in stream."""
        async def generator():
            yield ("token", {"content": "hi"})
            yield ("done", {"finished": True})

        result = [chunk async for chunk in sse_stream(generator())]
        assert len(result) == 2
        assert result[0].startswith(b"event: token")
        assert result[1].startswith(b"event: done")