"""SSE streaming utilities for chat responses."""

import json
from enum import Enum
from typing import AsyncIterator

SSE_EVENT_TYPES = frozenset(
    {"token", "tool_call_start", "tool_call_result", "error", "done", "usage"}
)


class SSEEventType(str, Enum):
    """Supported SSE event types."""

    TOKEN = "token"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"
    ERROR = "error"
    DONE = "done"
    USAGE = "usage"


def encode_sse_event(event_type: str, data: dict) -> bytes:
    """Encode a dict as an SSE event.

    Format: ``event: <type>\\ndata: <json>\\n\\n``
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n".encode("utf-8")


async def sse_stream(
    events: AsyncIterator[tuple[str, dict]],
) -> AsyncIterator[bytes]:
    """Yield SSE-encoded bytes from an async event iterator."""
    async for event_type, data in events:
        yield encode_sse_event(event_type, data)