from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.chatbot.service import ChatOrchestrator
from app.chatbot.tools import ToolContext, ToolDefinition, ToolRegistry
from app.database import Conversation, Message
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
async def test_orchestrator_persists_job_id_when_tool_returns_one(
    db_session, regular_user, conversation, mocker
):
    job_id = uuid4()

    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"job_id": str(job_id), "status": "created"}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="create_job",
            description="Create a job",
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
                LLMChunk(type="usage", tokens_in=5, tokens_out=1),
                LLMChunk(type="done"),
            ],
            [
                LLMChunk(type="text", content="Done"),
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
    async def _fake_resolve(model_id: str) -> Any:
        return llm
    orchestrator._resolve_llm = _fake_resolve

    ctx = ToolContext(user_id=str(regular_user.id), db=db_session, request_id="req1")
    events = [
        event
        async for event in orchestrator.run_turn(
            conversation.id,
            "create a video",
            None,
            "test-model",
            ctx,
        )
    ]

    assert any(e[0] == "tool_call_result" and e[1].get("result", {}).get("job_id") for e in events)

    rows = (await db_session.execute(select(Message).order_by(Message.created_at))).scalars().all()
    assistant_messages = [r for r in rows if r.role == "assistant"]
    assert len(assistant_messages) == 2

    assert assistant_messages[0].job_id == job_id
    assert assistant_messages[1].job_id == job_id
    assert "Done" in assistant_messages[1].content


@pytest.mark.asyncio
async def test_orchestrator_ignores_invalid_job_id(
    db_session, regular_user, conversation, mocker
):
    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"job_id": "not-a-uuid", "status": "created"}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="create_job",
            description="Create a job",
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
                LLMChunk(type="usage", tokens_in=5, tokens_out=1),
                LLMChunk(type="done"),
            ],
            [
                LLMChunk(type="text", content="Done"),
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
    async def _fake_resolve(model_id: str) -> Any:
        return llm
    orchestrator._resolve_llm = _fake_resolve

    ctx = ToolContext(user_id=str(regular_user.id), db=db_session, request_id="req1")
    async for _ in orchestrator.run_turn(
        conversation.id,
        "create a video",
        None,
        "test-model",
        ctx,
    ):
        pass

    rows = (await db_session.execute(select(Message).order_by(Message.created_at))).scalars().all()
    assistant_messages = [r for r in rows if r.role == "assistant"]
    assert len(assistant_messages) == 2
    assert assistant_messages[0].job_id is None
    assert assistant_messages[1].job_id is None
