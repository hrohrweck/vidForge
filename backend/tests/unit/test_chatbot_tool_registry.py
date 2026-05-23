"""Tests for the built-in tool registry and dispatch."""

import pytest

from app.chatbot.tools import (
    ToolContext,
    ToolDefinition,
    ToolRegistry,
    dispatch,
)


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_basic_definition(self):
        """ToolDefinition stores name, description, schema, handler."""
        async def handler(ctx, args):
            return {"ok": True}

        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            handler=handler,
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.input_schema == {"type": "object"}
        assert callable(tool.handler)

    def test_handler_is_async(self):
        """Handler must be an async callable."""
        async def handler(ctx, args):
            return {"ok": True}

        tool = ToolDefinition(
            name="sync_like",
            description="desc",
            input_schema={"type": "object"},
            handler=handler,
        )
        import asyncio

        async def call_it():
            result = await tool.handler(None, {})
            return result

        assert asyncio.run(call_it()) == {"ok": True}


class TestToolContext:
    """Tests for ToolContext dataclass."""

    def test_fields(self):
        """ToolContext holds user_id, db, request_id."""
        ctx = ToolContext(user_id="u1", db=None, request_id="req1")
        assert ctx.user_id == "u1"
        assert ctx.db is None
        assert ctx.request_id == "req1"

    def test_optional_fields(self):
        """ToolContext optional fields have sane defaults."""
        ctx = ToolContext(user_id="u1")
        assert ctx.db is None
        assert ctx.request_id == ""


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_register_and_get(self):
        """register() makes tool available via get()."""
        registry = ToolRegistry()

        async def handler(ctx, args):
            return {"ok": True}

        registry.register(
            ToolDefinition(
                name="my_tool",
                description="desc",
                input_schema={"type": "object"},
                handler=handler,
            )
        )

        tool = registry.get("my_tool")
        assert tool is not None
        assert tool.name == "my_tool"

    def test_get_unknown_returns_none(self):
        """get() returns None for unregistered tools."""
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_all_empty(self):
        """list_all() returns empty dict when nothing registered."""
        registry = ToolRegistry()
        assert registry.list_all() == {}

    def test_list_all_returns_copy(self):
        """list_all() returns a copy of the internal dict."""
        registry = ToolRegistry()

        async def h(ctx, args):
            return {}

        registry.register(
            ToolDefinition(
                name="tool1",
                description="d1",
                input_schema={},
                handler=h,
            )
        )
        registry.register(
            ToolDefinition(
                name="tool2",
                description="d2",
                input_schema={},
                handler=h,
            )
        )

        all_tools = registry.list_all()
        assert "tool1" in all_tools
        assert "tool2" in all_tools
        assert len(all_tools) == 2

    def test_to_openai_format(self):
        """to_openai_format() returns proper OpenAI tool format."""
        registry = ToolRegistry()

        async def h(ctx, args):
            return {}

        registry.register(
            ToolDefinition(
                name="create_job",
                description="Creates a new video generation job",
                input_schema={
                    "type": "object",
                    "properties": {
                        "template_id": {"type": "string"},
                    },
                },
                handler=h,
            )
        )

        result = registry.to_openai_format()
        assert result == [
            {
                "type": "function",
                "function": {
                    "name": "create_job",
                    "description": "Creates a new video generation job",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "template_id": {"type": "string"},
                        },
                    },
                },
            }
        ]

    def test_to_openai_format_multiple(self):
        """Multiple tools formatted correctly."""
        registry = ToolRegistry()

        async def h(ctx, args):
            return {}

        registry.register(
            ToolDefinition(
                name="tool_a",
                description="First tool",
                input_schema={"type": "object", "properties": {}},
                handler=h,
            )
        )
        registry.register(
            ToolDefinition(
                name="tool_b",
                description="Second tool",
                input_schema={"type": "object", "properties": {}},
                handler=h,
            )
        )

        result = registry.to_openai_format()
        assert len(result) == 2
        names = {r["function"]["name"] for r in result}
        assert names == {"tool_a", "tool_b"}


class TestDispatch:
    """Tests for the dispatch() helper."""

    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        """dispatch() calls the correct handler and returns result."""
        registry = ToolRegistry()

        async def my_handler(ctx, args):
            return {"job_id": "123"}

        registry.register(
            ToolDefinition(
                name="create_job",
                description="desc",
                input_schema={},
                handler=my_handler,
            )
        )

        ctx = ToolContext(user_id="u1", db=None, request_id="req1")
        result = await dispatch("create_job", {"template_id": "t1"}, ctx, registry)
        assert result == {"job_id": "123"}

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self):
        """dispatch() returns standardized error for unknown tool."""
        registry = ToolRegistry()
        ctx = ToolContext(user_id="u1")

        result = await dispatch("does_not_exist", {}, ctx, registry)

        assert "error" in result
        assert result["error"] == "unknown_tool"
        assert "available_tools" in result

    @pytest.mark.asyncio
    async def test_dispatch_handler_raises(self):
        """dispatch() catches handler exceptions and returns error shape."""
        registry = ToolRegistry()

        async def bad_handler(ctx, args):
            raise ValueError("something went wrong")

        registry.register(
            ToolDefinition(
                name="bad_tool",
                description="desc",
                input_schema={},
                handler=bad_handler,
            )
        )

        ctx = ToolContext(user_id="u1")
        result = await dispatch("bad_tool", {}, ctx, registry)

        assert "error" in result
        assert result["error"] == "handler_error"
        assert "message" in result
        assert "ValueError" in result["message"]
        assert "something went wrong" in result["message"]

    @pytest.mark.asyncio
    async def test_dispatch_available_tools_in_error(self):
        """Error response includes names of available tools."""
        registry = ToolRegistry()

        async def h1(ctx, args):
            return {}

        async def h2(ctx, args):
            return {}

        registry.register(
            ToolDefinition(
                name="tool_alpha",
                description="Alpha tool",
                input_schema={},
                handler=h1,
            )
        )
        registry.register(
            ToolDefinition(
                name="tool_beta",
                description="Beta tool",
                input_schema={},
                handler=h2,
            )
        )

        ctx = ToolContext(user_id="u1")
        result = await dispatch("unknown", {}, ctx, registry)

        assert "available_tools" in result
        tool_names = result["available_tools"]
        assert "tool_alpha" in tool_names
        assert "tool_beta" in tool_names