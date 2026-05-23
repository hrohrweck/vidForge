"""Remote MCP client for tool discovery and execution."""

from __future__ import annotations

import json
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.chatbot.crypto import decrypt_credentials

TOOL_CACHE_TTL_SECONDS = 60.0
SESSION_TTL_SECONDS = 60.0
TOOL_CALL_TIMEOUT_SECONDS = 30.0


class MCPServerLike(Protocol):
    """Subset of the MCPServer model needed by the client manager."""

    slug: str
    url: str
    auth_type: str
    encrypted_credentials: bytes | None
    enabled: bool

@dataclass
class ToolDefinition:
    """Definition of a callable tool available to the chatbot LLM."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Any


@dataclass
class RemoteToolResult:
    """Normalized remote MCP tool result returned to chatbot callers."""

    content: list[dict[str, Any]] = field(default_factory=list)
    structured_content: dict[str, Any] | None = None
    is_error: bool = False
    error: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "content": self.content,
            "structured_content": self.structured_content,
            "is_error": self.is_error,
        }
        if self.error is not None:
            data["error"] = self.error
        if self.message is not None:
            data["message"] = self.message
        return data


ToolResult = RemoteToolResult


@dataclass
class _ServerConnection:
    server: MCPServerLike
    client: httpx.AsyncClient
    stack: AsyncExitStack
    session: ClientSession
    expires_at: float
    tools: list[ToolDefinition] | None = None
    tools_expires_at: float = 0.0


class MCPClientManager:
    """Manage remote streamable HTTP MCP sessions keyed by server slug."""

    def __init__(
        self,
        *,
        session_ttl_seconds: float = SESSION_TTL_SECONDS,
        tool_cache_ttl_seconds: float = TOOL_CACHE_TTL_SECONDS,
        call_timeout_seconds: float = TOOL_CALL_TIMEOUT_SECONDS,
    ) -> None:
        self._servers: dict[str, MCPServerLike] = {}
        self._connections: dict[str, _ServerConnection] = {}
        self._session_ttl_seconds = session_ttl_seconds
        self._tool_cache_ttl_seconds = tool_cache_ttl_seconds
        self._call_timeout_seconds = call_timeout_seconds

    def register_server(self, server: MCPServerLike) -> None:
        """Register or replace an MCP server for future calls."""
        self._servers[server.slug] = server

    async def connect(self, server: MCPServerLike) -> ClientSession:
        """Open or reuse a cached streamable HTTP MCP session for ``server``."""
        self.register_server(server)
        now = time.monotonic()
        cached = self._connections.get(server.slug)
        if cached and cached.expires_at > now:
            return cached.session

        if cached:
            await self._close_connection(server.slug)

        headers = self._build_auth_headers(server)
        client = httpx.AsyncClient(headers=headers, timeout=self._call_timeout_seconds)
        stack = AsyncExitStack()
        try:
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamable_http_client(server.url, http_client=client)
            )
            session = await stack.enter_async_context(
                ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=self._call_timeout_seconds),
                )
            )
            await session.initialize()
        except Exception:
            await stack.aclose()
            await client.aclose()
            raise

        connection = _ServerConnection(
            server=server,
            client=client,
            stack=stack,
            session=session,
            expires_at=now + self._session_ttl_seconds,
        )
        self._connections[server.slug] = connection
        return session

    async def list_tools(self, server_slug: str) -> list[ToolDefinition]:
        """Return remote MCP tools namespaced as ``{server_slug}__{tool_name}``."""
        server = self._servers.get(server_slug)
        if server is None:
            return []

        connection = await self._get_connection(server)
        if connection is None:
            return []

        now = time.monotonic()
        if connection.tools is not None and connection.tools_expires_at > now:
            return list(connection.tools)

        try:
            result = await connection.session.list_tools()
        except Exception:
            await self._close_connection(server_slug)
            return []

        tools = [self._to_tool_definition(server_slug, tool) for tool in result.tools]
        connection.tools = tools
        connection.tools_expires_at = now + self._tool_cache_ttl_seconds
        return list(tools)

    async def call_tool(self, qualified_name: str, args: dict[str, Any]) -> RemoteToolResult:
        """Route a namespaced tool call to its remote MCP server."""
        server_slug, tool_name = self._split_qualified_name(qualified_name)
        if not server_slug or not tool_name:
            return self._unavailable_result("Invalid MCP tool name")

        server = self._servers.get(server_slug)
        if server is None:
            return self._unavailable_result("MCP server is not registered")

        connection = await self._get_connection(server)
        if connection is None:
            return self._unavailable_result("MCP server is unavailable")

        try:
            result = await connection.session.call_tool(
                tool_name,
                args,
                read_timeout_seconds=timedelta(seconds=self._call_timeout_seconds),
            )
        except Exception:
            await self._close_connection(server_slug)
            return self._unavailable_result("MCP server is unavailable")

        return RemoteToolResult(
            content=[self._content_to_dict(item) for item in result.content],
            structured_content=result.structuredContent,
            is_error=result.isError,
        )

    async def health_check(self, server: MCPServerLike) -> bool:
        """Return whether ``server`` accepts a streamable HTTP MCP session."""
        try:
            await self.connect(server)
        except Exception:
            return False
        return True

    async def close(self) -> None:
        """Close all cached MCP sessions and HTTP clients."""
        for slug in list(self._connections):
            await self._close_connection(slug)

    async def _get_connection(self, server: MCPServerLike) -> _ServerConnection | None:
        try:
            await self.connect(server)
        except Exception:
            return None
        return self._connections.get(server.slug)

    async def _close_connection(self, server_slug: str) -> None:
        connection = self._connections.pop(server_slug, None)
        if connection is None:
            return
        await connection.stack.aclose()
        await connection.client.aclose()

    def _to_tool_definition(self, server_slug: str, tool: Any) -> ToolDefinition:
        tool_name = tool.name

        async def handler(_context: Any, args: dict[str, Any]) -> dict[str, Any]:
            return (await self.call_tool(f"{server_slug}__{tool_name}", args)).to_dict()

        return ToolDefinition(
            name=f"{server_slug}__{tool_name}",
            description=tool.description or "",
            input_schema=tool.inputSchema,
            handler=handler,
        )

    def _build_auth_headers(self, server: MCPServerLike) -> dict[str, str]:
        if server.auth_type == "none" or not server.encrypted_credentials:
            return {}

        plaintext = decrypt_credentials(server.encrypted_credentials)
        if server.auth_type == "bearer":
            return {"Authorization": f"Bearer {plaintext}"}
        if server.auth_type == "headers":
            parsed = json.loads(plaintext)
            if not isinstance(parsed, dict):
                raise ValueError("MCP header credentials must decrypt to a JSON object")
            return {str(key): str(value) for key, value in parsed.items()}

        return {}

    def _split_qualified_name(self, qualified_name: str) -> tuple[str, str]:
        if "__" not in qualified_name:
            return "", ""
        server_slug, tool_name = qualified_name.split("__", 1)
        return server_slug, tool_name

    def _content_to_dict(self, item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        if isinstance(item, dict):
            return item
        return {"type": "text", "text": str(item)}

    def _unavailable_result(self, message: str) -> RemoteToolResult:
        return RemoteToolResult(
            is_error=True,
            error="mcp_server_unavailable",
            message=message,
        )
