"""Tests for the chat orchestration loop."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.chatbot.service import SYSTEM_PROMPT, ChatOrchestrator
from app.chatbot.tools import ToolContext, ToolDefinition, ToolRegistry
from app.database import ChatTokenUsage, Conversation, Message
from app.services.llm_service import LLMChunk


class FakeLLM:
    def __init__(self, streams: list[list[LLMChunk]]) -> None:
        self.streams = streams
        self.calls: list[dict[str, Any]] = []

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        self.calls.append({"messages": messages, "model": model, "tools": tools})
        stream = self.streams.pop(0) if self.streams else []
        for chunk in stream:
            yield chunk


class FakeMCPManager:
    def __init__(self) -> None:
        self.registered: list[str] = []

    def register_server(self, server) -> None:
        self.registered.append(server.slug)

    async def list_tools(self, server_slug: str) -> list:
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        raise AssertionError(f"unexpected MCP tool call: {name}")


async def collect_events(orchestrator: ChatOrchestrator, conversation, user) -> list[tuple[str, dict]]:
    ctx = ToolContext(user_id=str(user.id), db=orchestrator.db, request_id="req1")
    return [
        event
        async for event in orchestrator.run_turn(
            conversation.id,
            "hello",
            None,
            "test-model",
            ctx,
        )
    ]


@pytest.fixture
async def conversation(db_session, regular_user):
    conversation = Conversation(
        user_id=regular_user.id,
        title="Chat",
        model_id="test-model",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest.mark.asyncio
async def test_run_turn_streams_final_answer_and_records_usage(db_session, regular_user, conversation):
    llm = FakeLLM(
        [
            [
                LLMChunk(type="text", content="Hel"),
                LLMChunk(type="text", content="lo"),
                LLMChunk(type="usage", tokens_in=8, tokens_out=2),
                LLMChunk(type="done"),
            ]
        ]
    )
    orchestrator = ChatOrchestrator(db_session, llm=llm, mcp_manager=FakeMCPManager())

    events = await collect_events(orchestrator, conversation, regular_user)

    assert events == [
        ("token", {"content": "Hel"}),
        ("token", {"content": "lo"}),
        ("usage", {"tokens_in": 8, "tokens_out": 2}),
        ("done", {}),
    ]
    assert llm.calls[0]["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert llm.calls[0]["model"] == "test-model"

    rows = (await db_session.execute(select(Message).order_by(Message.created_at))).scalars().all()
    assert [(row.role, row.content) for row in rows] == [("user", "hello"), ("assistant", "Hello")]
    usage = (await db_session.execute(select(ChatTokenUsage))).scalar_one()
    assert usage.tokens_in == 8
    assert usage.tokens_out == 2


@pytest.mark.asyncio
async def test_run_turn_dispatches_tool_serially_then_continues(db_session, regular_user, conversation):
    calls: list[dict[str, Any]] = []

    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        return {"echo": args["text"]}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo text",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            handler=handler,
        )
    )
    llm = FakeLLM(
        [
            [
                LLMChunk(
                    type="tool_call",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "function": {"name": "echo", "arguments": '{"text": "hi"}'},
                        }
                    ],
                ),
                LLMChunk(type="usage", tokens_in=5, tokens_out=1),
                LLMChunk(type="done"),
            ],
            [
                LLMChunk(type="text", content="Tool said hi"),
                LLMChunk(type="usage", tokens_in=6, tokens_out=3),
                LLMChunk(type="done"),
            ],
        ]
    )
    orchestrator = ChatOrchestrator(
        db_session,
        llm=llm,
        registry=registry,
        mcp_manager=FakeMCPManager(),
    )

    events = await collect_events(orchestrator, conversation, regular_user)

    assert calls == [{"text": "hi"}]
    assert events == [
        ("tool_call_start", {"id": "call_1", "name": "echo", "arguments": {"text": "hi"}}),
        (
            "tool_call_result",
            {"id": "call_1", "name": "echo", "kind": "tool_result", "result": {"echo": "hi"}},
        ),
        ("token", {"content": "Tool said hi"}),
        ("usage", {"tokens_in": 11, "tokens_out": 4}),
        ("done", {}),
    ]
    second_call_roles = [message["role"] for message in llm.calls[1]["messages"]]
    assert second_call_roles[-2:] == ["assistant", "tool"]


@pytest.mark.asyncio
async def test_run_turn_emits_error_when_loop_bound_is_hit(db_session, regular_user, conversation):
    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"again": True}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="again",
            description="Loop tool",
            input_schema={"type": "object"},
            handler=handler,
        )
    )
    streams = [
        [
            LLMChunk(
                type="tool_call",
                tool_calls=[{"id": f"call_{index}", "function": {"name": "again", "arguments": "{}"}}],
            ),
            LLMChunk(type="done"),
        ]
        for index in range(8)
    ]
    orchestrator = ChatOrchestrator(
        db_session,
        llm=FakeLLM(streams),
        registry=registry,
        mcp_manager=FakeMCPManager(),
    )
    orchestrator.max_iterations = 8

    events = await collect_events(orchestrator, conversation, regular_user)

    assert events[-2][0] == "error"
    assert events[-2][1]["reason"] == "iteration_limit_exceeded"
    assert events[-1] == ("done", {})


@pytest.mark.asyncio
async def test_run_turn_pauses_on_create_job_draft(db_session, regular_user, conversation):
    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"action": "draft", "payload": {"title": args["prompt"]}}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="create_job",
            description="Create job",
            input_schema={"type": "object"},
            handler=handler,
        )
    )
    llm = FakeLLM(
        [
            [
                LLMChunk(
                    type="tool_call",
                    tool_calls=[
                        {
                            "id": "draft_1",
                            "function": {
                                "name": "create_job",
                                "arguments": '{"prompt": "make a video"}',
                            },
                        }
                    ],
                ),
                LLMChunk(type="usage", tokens_in=4, tokens_out=1),
                LLMChunk(type="done"),
            ],
            [
                LLMChunk(type="text", content="Draft ready."),
                LLMChunk(type="usage", tokens_in=2, tokens_out=2),
                LLMChunk(type="done"),
            ],
        ]
    )
    orchestrator = ChatOrchestrator(
        db_session,
        llm=llm,
        registry=registry,
        mcp_manager=FakeMCPManager(),
    )

    events = await collect_events(orchestrator, conversation, regular_user)

    assert events == [
        (
            "tool_call_start",
            {"id": "draft_1", "name": "create_job", "arguments": {"prompt": "make a video"}},
        ),
        (
            "tool_call_result",
            {
                "id": "draft_1",
                "name": "create_job",
                "kind": "job_draft",
                "result": {"action": "draft", "payload": {"title": "make a video"}},
            },
        ),
        ("token", {"content": "Draft ready."}),
        ("usage", {"tokens_in": 6, "tokens_out": 3}),
        ("done", {}),
    ]
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_run_turn_pauses_after_successful_create_job(db_session, regular_user, conversation):
    job_id = uuid4()

    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"job_id": str(job_id), "status": "created"}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="create_job",
            description="Create job",
            input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}},
            handler=handler,
        )
    )
    llm = FakeLLM(
        [
            [
                LLMChunk(
                    type="tool_call",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "function": {
                                "name": "create_job",
                                "arguments": '{"prompt": "make a video"}',
                            },
                        }
                    ],
                ),
                LLMChunk(type="usage", tokens_in=4, tokens_out=1),
                LLMChunk(type="done"),
            ],
            [
                LLMChunk(type="text", content="Job created."),
                LLMChunk(type="usage", tokens_in=2, tokens_out=2),
                LLMChunk(type="done"),
            ],
        ]
    )
    orchestrator = ChatOrchestrator(
        db_session,
        llm=llm,
        registry=registry,
        mcp_manager=FakeMCPManager(),
    )

    events = await collect_events(orchestrator, conversation, regular_user)

    assert events == [
        (
            "tool_call_start",
            {"id": "call_1", "name": "create_job", "arguments": {"prompt": "make a video"}},
        ),
        (
            "tool_call_result",
            {
                "id": "call_1",
                "name": "create_job",
                "kind": "job_created",
                "result": {"job_id": str(job_id), "status": "created"},
            },
        ),
        ("token", {"content": "Job created."}),
        ("usage", {"tokens_in": 6, "tokens_out": 3}),
        ("done", {}),
    ]
    assert len(llm.calls) == 2

    rows = (await db_session.execute(select(Message).order_by(Message.created_at))).scalars().all()
    assistant_messages = [r for r in rows if r.role == "assistant"]
    assert len(assistant_messages) == 2
    assert assistant_messages[0].job_id == job_id
    assert assistant_messages[1].job_id == job_id
    assert "Job created." in assistant_messages[1].content


@pytest.mark.asyncio
async def test_run_turn_pauses_after_successful_batch_create_jobs(
    db_session, regular_user, conversation
):
    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"created_count": 2, "job_ids": [str(uuid4()), str(uuid4())]}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="batch_create_jobs",
            description="Batch create jobs",
            input_schema={"type": "object"},
            handler=handler,
        )
    )
    llm = FakeLLM(
        [
            [
                LLMChunk(
                    type="tool_call",
                    tool_calls=[
                        {
                            "id": "batch_1",
                            "function": {
                                "name": "batch_create_jobs",
                                "arguments": '{"template_id": "tmpl-1", "jobs": [{"prompt": "a"}]}',
                            },
                        }
                    ],
                ),
                LLMChunk(type="usage", tokens_in=4, tokens_out=1),
                LLMChunk(type="done"),
            ],
            [
                LLMChunk(type="text", content="All set."),
                LLMChunk(type="usage", tokens_in=2, tokens_out=2),
                LLMChunk(type="done"),
            ],
        ]
    )
    orchestrator = ChatOrchestrator(
        db_session,
        llm=llm,
        registry=registry,
        mcp_manager=FakeMCPManager(),
    )

    events = await collect_events(orchestrator, conversation, regular_user)

    assert events[-4][0] == "tool_call_result"
    assert events[-4][1]["name"] == "batch_create_jobs"
    assert events[-4][1]["kind"] == "job_created"
    assert events[-3] == ("token", {"content": "All set."})
    assert events[-2] == ("usage", {"tokens_in": 6, "tokens_out": 3})
    assert events[-1] == ("done", {})
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_message_with_image_attachment_non_vision_model(db_session, regular_user, conversation):
    """Image attachment + non-vision model → content is list with text + text note."""
    llm = FakeLLM(
        [
            [
                LLMChunk(type="text", content="Got it."),
                LLMChunk(type="usage", tokens_in=5, tokens_out=2),
                LLMChunk(type="done"),
            ]
        ]
    )
    orchestrator = ChatOrchestrator(db_session, llm=llm, mcp_manager=FakeMCPManager())

    ctx = ToolContext(user_id=str(regular_user.id), db=db_session, request_id="req1")
    attachments = [{"kind": "image", "url": "https://example.com/image.png", "mime_type": "image/png"}]

    events = [
        event
        async for event in orchestrator.run_turn(
            conversation.id,
            "look at this",
            attachments,
            "qwen3.6:35b",  # non-vision model
            ctx,
        )
    ]

    assert events[-2] == ("usage", {"tokens_in": 5, "tokens_out": 2})
    call_messages = llm.calls[0]["messages"]
    user_msg = next(m for m in call_messages if m["role"] == "user")
    assert isinstance(user_msg["content"], list)
    text_part = next(p for p in user_msg["content"] if p["type"] == "text")
    assert text_part["text"] == "look at this"
    note_part = next(p for p in user_msg["content"] if p["type"] == "text" and "Image attachment" in p["text"])
    assert "[Image attachment: model does not support vision]" in note_part["text"]


@pytest.mark.asyncio
async def test_run_turn_handles_tool_returning_list(db_session, regular_user, conversation):
    async def handler(ctx: ToolContext, args: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"name": "avatar-1"}, {"name": "avatar-2"}]

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="list_avatars",
            description="List avatars",
            input_schema={"type": "object"},
            handler=handler,
        )
    )
    llm = FakeLLM(
        [
            [
                LLMChunk(
                    type="tool_call",
                    tool_calls=[
                        {
                            "id": "call_list",
                            "function": {"name": "list_avatars", "arguments": "{}"},
                        }
                    ],
                ),
                LLMChunk(type="text", content="Found them."),
                LLMChunk(type="usage", tokens_in=5, tokens_out=2),
                LLMChunk(type="done"),
            ]
        ]
    )
    orchestrator = ChatOrchestrator(
        db_session,
        llm=llm,
        registry=registry,
        mcp_manager=FakeMCPManager(),
    )

    events = await collect_events(orchestrator, conversation, regular_user)

    assert events == [
        ("token", {"content": "Found them."}),
        (
            "tool_call_start",
            {"id": "call_list", "name": "list_avatars", "arguments": {}},
        ),
        (
            "tool_call_result",
            {
                "id": "call_list",
                "name": "list_avatars",
                "kind": "tool_result",
                "result": [{"name": "avatar-1"}, {"name": "avatar-2"}],
            },
        ),
        ("usage", {"tokens_in": 5, "tokens_out": 2}),
        ("done", {}),
    ]
