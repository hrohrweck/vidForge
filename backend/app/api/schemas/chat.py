from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class MessagePart(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    content: str | dict


class MessagePartTextual(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["text"] = "text"
    content: str


class MessagePartImageContent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["image"] = "image"
    content: str


class MessagePartAudioContent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["audio"] = "audio"
    content: str


class MessagePartScriptContent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["script"] = "script"
    content: dict


class ToolCall(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    arguments: dict[str, str]


class ToolResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tool_call_id: str
    output: str | None = None
    error: str | None = None


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None


class ConversationRename(BaseModel):
    title: str


class MessageCreate(BaseModel):
    content: str
    parts: list[MessagePart] | None = None
    parent_id: UUID | None = None


class ChatStreamMessageCreate(BaseModel):
    content: str
    model_id: str
    attachments: list[dict] | None = None
    confirm_draft_id: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    parts: list[MessagePart] | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    created_at: datetime

    @field_validator("tool_calls", mode="before")
    @classmethod
    def normalize_tool_calls(cls, v: object) -> object:
        """Normalize tool_calls from stored dict format to a list."""
        if isinstance(v, dict):
            return v.get("tool_calls", v)
        return v


class ChatStreamEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event: Literal[
        "message_start",
        "message_end",
        "message_delta",
        "tool_call_start",
        "tool_call_end",
        "tool_result",
        "error",
    ]
    data: dict


class ChatStreamMessageStart(BaseModel):
    event: Literal["message_start"] = "message_start"
    message_id: UUID
    role: Literal["user", "assistant", "system", "tool"]


class ChatStreamMessageEnd(BaseModel):
    event: Literal["message_end"] = "message_end"
    message_id: UUID


class ChatStreamMessageDelta(BaseModel):
    event: Literal["message_delta"] = "message_delta"
    content: str


class ChatStreamToolCallStart(BaseModel):
    event: Literal["tool_call_start"] = "tool_call_start"
    tool_call_id: str
    name: str
    arguments: dict[str, str] | None = None


class ChatStreamToolCallEnd(BaseModel):
    event: Literal["tool_call_end"] = "tool_call_end"
    tool_call_id: str


class ChatStreamToolResult(BaseModel):
    event: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    output: str | None = None
    error: str | None = None


class ChatStreamError(BaseModel):
    event: Literal["error"] = "error"
    error: str
