"""Tests for the remote streamable HTTP MCP client manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from app.chatbot.crypto import encrypt_credentials
from app.chatbot.mcp_client import MCPClientManager


@dataclass
class StubMCPServerConfig:
    slug: str
    url: str
    auth_type: str = "none"
    encrypted_credentials: bytes | None = None
    enabled: bool = True


@dataclass
class StubMCPServer:
    required_headers: dict[str, str]
    received_headers: dict[str, str] | None = None
    list_tools_calls: int = 0
    call_tool_calls: int = 0

    def assert_auth(self, headers: dict[str, str]) -> None:
        self.received_headers = headers
        for key, expected_value in self.required_headers.items():
            if headers.get(key) != expected_value:
                raise OSError("remote MCP server returned 401")

    async def list_tools(self) -> ListToolsResult:
        self.list_tools_calls += 1
        return ListToolsResult(
            tools=[
                Tool(
                    name="echo",
                    description="Echo input text",
                    inputSchema={
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                )
            ]
        )

    async def call_tool(self, name: str, arguments: dict[str, Any], **_kwargs: Any) -> CallToolResult:
        self.call_tool_calls += 1
        if name == "echo":
            return CallToolResult(content=[TextContent(type="text", text=f"echo:{arguments['text']}")])
        return CallToolResult(content=[TextContent(type="text", text="unknown")])


class StubClientSession:
    def __init__(self, stub: StubMCPServer, headers: dict[str, str]):
        self.stub = stub
        self.headers = {key.lower(): value for key, value in headers.items()}

    async def initialize(self):
        self.stub.assert_auth(self.headers)

    async def list_tools(self):
        return await self.stub.list_tools()

    async def call_tool(self, name, arguments, **kwargs):
        return await self.stub.call_tool(name, arguments, **kwargs)


@pytest.fixture
def stub_mcp_server():
    return StubMCPServer(required_headers={})


@pytest.fixture
async def manager(stub_mcp_server, monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_streamable_http_client(url, *, http_client=None, terminate_on_close=True):
        yield object(), object(), lambda: "session-id"

    class FakeClientSession:
        def __init__(self, *_args, **_kwargs):
            self._session = StubClientSession(stub_mcp_server, captured_headers)

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *_exc_info):
            return False

    captured_headers: dict[str, str] = {}

    class PatchedAsyncClient:
        def __init__(self, *args, **kwargs):
            captured_headers.clear()
            captured_headers.update(kwargs.get("headers") or {})

        async def aclose(self):
            return None

    monkeypatch.setattr("app.chatbot.mcp_client.streamable_http_client", fake_streamable_http_client)
    monkeypatch.setattr("app.chatbot.mcp_client.ClientSession", FakeClientSession)
    monkeypatch.setattr("app.chatbot.mcp_client.httpx.AsyncClient", PatchedAsyncClient)

    client_manager = MCPClientManager(session_ttl_seconds=60, tool_cache_ttl_seconds=60)
    try:
        yield client_manager
    finally:
        await client_manager.close()


@pytest.mark.asyncio
async def test_list_tools_namespaces_remote_tools(manager, stub_mcp_server):
    server = StubMCPServerConfig(slug="demo", url="http://testserver/mcp")
    await manager.connect(server)

    tools = await manager.list_tools("demo")

    assert [tool.name for tool in tools] == ["demo__echo"]
    assert tools[0].description == "Echo input text"
    assert tools[0].input_schema["properties"]["text"] == {"type": "string"}
    assert stub_mcp_server.list_tools_calls == 1


@pytest.mark.asyncio
async def test_list_tools_uses_ttl_cache(manager, stub_mcp_server):
    server = StubMCPServerConfig(slug="demo", url="http://testserver/mcp")
    await manager.connect(server)

    first = await manager.list_tools("demo")
    second = await manager.list_tools("demo")

    assert first[0].name == second[0].name
    assert stub_mcp_server.list_tools_calls == 1


@pytest.mark.asyncio
async def test_call_tool_routes_qualified_name(manager, stub_mcp_server):
    server = StubMCPServerConfig(slug="demo", url="http://testserver/mcp")
    await manager.connect(server)

    result = await manager.call_tool("demo__echo", {"text": "hello"})

    assert result.to_dict() == {
        "content": [{"type": "text", "text": "echo:hello", "annotations": None, "meta": None}],
        "structured_content": None,
        "is_error": False,
    }
    assert stub_mcp_server.call_tool_calls == 1


@pytest.mark.asyncio
async def test_bearer_auth_uses_decrypted_token(manager, stub_mcp_server):
    stub_mcp_server.required_headers = {"authorization": "Bearer secret-token"}
    server = StubMCPServerConfig(
        slug="secure",
        url="http://testserver/mcp",
        auth_type="bearer",
        encrypted_credentials=encrypt_credentials("secret-token"),
    )

    assert await manager.health_check(server) is True
    tools = await manager.list_tools("secure")

    assert [tool.name for tool in tools] == ["secure__echo"]


@pytest.mark.asyncio
async def test_custom_headers_auth_uses_decrypted_json(manager, stub_mcp_server):
    stub_mcp_server.required_headers = {"x-api-key": "secret-key"}
    server = StubMCPServerConfig(
        slug="headers",
        url="http://testserver/mcp",
        auth_type="headers",
        encrypted_credentials=encrypt_credentials('{"X-API-Key": "secret-key"}'),
    )

    assert await manager.health_check(server) is True


@pytest.mark.asyncio
async def test_network_errors_return_unavailable_result(manager):
    result = await manager.call_tool("missing__echo", {"text": "hello"})

    assert result.to_dict() == {
        "content": [],
        "structured_content": None,
        "is_error": True,
        "error": "mcp_server_unavailable",
        "message": "MCP server is not registered",
    }


@pytest.mark.asyncio
async def test_health_check_returns_false_for_failed_auth(manager, stub_mcp_server):
    stub_mcp_server.required_headers = {"authorization": "Bearer expected"}
    server = StubMCPServerConfig(
        slug="secure",
        url="http://testserver/mcp",
        auth_type="bearer",
        encrypted_credentials=encrypt_credentials("wrong"),
    )

    assert await manager.health_check(server) is False
