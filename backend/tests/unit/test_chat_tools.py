"""Tests for the new chatbot tools: generate_media, list_projects, create_project."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.chatbot.tools import (
    ToolContext,
    ToolRegistry,
    create_builtin_registry,
    dispatch,
)
from app.database import Project


@pytest.fixture
def registry():
    """Fresh built-in registry for each test."""
    return create_builtin_registry()


@pytest.fixture
def tool_context(regular_user):
    """ToolContext with user_id from regular_user fixture."""

    def _make(db_session=None):
        return ToolContext(user_id=str(regular_user.id), db=db_session)

    return _make


class TestGenerateMediaTool:
    """Tests for generate_media tool."""

    def test_parameters_schema_is_valid(self, registry):
        """generate_media input_schema has expected structure and required fields."""
        tool = registry.get("generate_media")
        assert tool is not None
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "model_id" in schema["properties"]
        assert "prompt" in schema["properties"]
        assert "aspect_ratio" in schema["properties"]
        assert "duration" in schema["properties"]
        assert schema["required"] == ["model_id", "prompt"]

    @pytest.mark.asyncio
    async def test_queues_media_generation(self, registry, tool_context, mocker):
        """generate_media dispatches a Celery task and returns task_id."""
        mock_task = MagicMock()
        mock_task.id = "celery-task-abc123"
        mock_delay = mocker.patch(
            "app.workers.tasks.generate_quick_media.delay",
            return_value=mock_task,
        )

        ctx = tool_context()
        result = await dispatch(
            "generate_media",
            {
                "model_id": "flux1-schnell",
                "prompt": "a serene mountain lake at sunset",
                "aspect_ratio": "16:9",
                "duration": 5,
            },
            ctx,
            registry,
        )

        assert "error" not in result
        assert result["status"] == "queued"
        assert result["task_id"] == "celery-task-abc123"
        mock_delay.assert_called_once()
        call_kwargs = mock_delay.call_args.kwargs
        assert call_kwargs["user_id"] == ctx.user_id
        assert call_kwargs["model_id"] == "flux1-schnell"
        assert call_kwargs["prompt"] == "a serene mountain lake at sunset"

    @pytest.mark.asyncio
    async def test_missing_model_id_returns_error(self, registry, tool_context):
        """generate_media without model_id returns validation error."""
        ctx = tool_context()
        result = await dispatch(
            "generate_media",
            {"prompt": "test"},
            ctx,
            registry,
        )
        assert result["error"] == "missing_argument"
        assert "model_id" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_prompt_returns_error(self, registry, tool_context):
        """generate_media without prompt returns validation error."""
        ctx = tool_context()
        result = await dispatch(
            "generate_media",
            {"model_id": "flux1-schnell"},
            ctx,
            registry,
        )
        assert result["error"] == "missing_argument"
        assert "prompt" in result["message"]

    @pytest.mark.asyncio
    async def test_uses_defaults_for_optional_params(self, registry, tool_context, mocker):
        """generate_media uses default values for aspect_ratio and duration."""
        mock_task = MagicMock()
        mock_task.id = "task-defaults"
        mock_delay = mocker.patch(
            "app.workers.tasks.generate_quick_media.delay",
            return_value=mock_task,
        )

        ctx = tool_context()
        await dispatch(
            "generate_media",
            {"model_id": "flux1-schnell", "prompt": "test"},
            ctx,
            registry,
        )

        call_kwargs = mock_delay.call_args.kwargs
        assert call_kwargs["aspect_ratio"] == "1:1"
        assert call_kwargs["duration"] == 5


class TestListProjectsTool:
    """Tests for list_projects tool."""

    @pytest.mark.asyncio
    async def test_returns_projects_array(self, db_session, registry, tool_context):
        """list_projects returns a projects array scoped to the user."""
        ctx = tool_context(db_session)
        result = await dispatch("list_projects", {}, ctx, registry)
        assert "error" not in result
        assert "projects" in result
        assert isinstance(result["projects"], list)
        assert "count" in result

    @pytest.mark.asyncio
    async def test_includes_user_projects(self, db_session, registry, tool_context, regular_user):
        """list_projects returns projects belonging to the user."""
        project = Project(
            user_id=regular_user.id,
            title="My Test Project",
            description="A project for testing",
        )
        db_session.add(project)
        await db_session.commit()

        ctx = tool_context(db_session)
        result = await dispatch("list_projects", {}, ctx, registry)
        assert result["count"] >= 1
        project_ids = [p["id"] for p in result["projects"]]
        assert str(project.id) in project_ids
        found = next(p for p in result["projects"] if p["id"] == str(project.id))
        assert found["title"] == "My Test Project"
        assert found["description"] == "A project for testing"

    @pytest.mark.asyncio
    async def test_respects_limit(self, db_session, registry, tool_context, regular_user):
        """list_projects respects the limit parameter."""
        for i in range(5):
            db_session.add(Project(user_id=regular_user.id, title=f"Project {i}"))
        await db_session.commit()

        ctx = tool_context(db_session)
        result = await dispatch("list_projects", {"limit": 2}, ctx, registry)
        assert len(result["projects"]) <= 2

    @pytest.mark.asyncio
    async def test_empty_for_user_with_no_projects(self, db_session, registry, tool_context):
        """list_projects returns empty array for user with no projects."""
        ctx = tool_context(db_session)
        result = await dispatch("list_projects", {}, ctx, registry)
        assert result["projects"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_missing_db_returns_error(self, registry, tool_context):
        """list_projects without db session returns error."""
        ctx = tool_context()
        result = await dispatch("list_projects", {}, ctx, registry)
        assert result["error"] == "missing_db"


class TestCreateProjectTool:
    """Tests for create_project tool."""

    @pytest.mark.asyncio
    async def test_creates_new_project(self, db_session, registry, tool_context):
        """create_project creates a new Project row and returns it."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "create_project",
            {"title": "New Video Project", "description": "A chatbot-created project"},
            ctx,
            registry,
        )

        assert "error" not in result
        assert result["title"] == "New Video Project"
        assert result["description"] == "A chatbot-created project"
        assert "id" in result
        assert "created_at" in result
        assert "updated_at" in result

        from uuid import UUID as _UUID
        from sqlalchemy import select

        db_result = await db_session.execute(
            select(Project).where(Project.id == _UUID(result["id"]))
        )
        project = db_result.scalar_one()
        assert project.title == "New Video Project"

    @pytest.mark.asyncio
    async def test_without_description(self, db_session, registry, tool_context):
        """create_project works without optional description."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "create_project",
            {"title": "Minimal Project"},
            ctx,
            registry,
        )
        assert "error" not in result
        assert result["title"] == "Minimal Project"
        assert result["description"] is None

    @pytest.mark.asyncio
    async def test_missing_title_returns_error(self, db_session, registry, tool_context):
        """create_project without title returns validation error."""
        ctx = tool_context(db_session)
        result = await dispatch("create_project", {}, ctx, registry)
        assert result["error"] == "missing_argument"
        assert "title" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_db_returns_error(self, registry, tool_context):
        """create_project without db session returns error."""
        ctx = tool_context()
        result = await dispatch(
            "create_project",
            {"title": "Test"},
            ctx,
            registry,
        )
        assert result["error"] == "missing_db"

    @pytest.mark.asyncio
    async def test_project_scoped_to_user(self, db_session, registry, tool_context, regular_user):
        """Projects are scoped to the creating user."""
        from app.database import User
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        other_user = User(
            id=uuid4(),
            email="other-project@example.com",
            hashed_password=pwd_context.hash("pass"),
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()

        ctx_a = tool_context(db_session)
        result = await dispatch(
            "create_project",
            {"title": "User A Project"},
            ctx_a,
            registry,
        )

        # User B should see empty projects list
        ctx_b = ToolContext(user_id=str(other_user.id), db=db_session)
        b_result = await dispatch("list_projects", {}, ctx_b, registry)
        project_ids = [p["id"] for p in b_result["projects"]]
        assert result["id"] not in project_ids


class TestToolRegistryIncludesAll:
    """Tests that the registry includes all new tools."""

    def test_registry_includes_generate_media(self, registry):
        """Registry includes the generate_media tool."""
        tool = registry.get("generate_media")
        assert tool is not None
        assert tool.name == "generate_media"
        assert callable(tool.handler)

    def test_registry_includes_list_projects(self, registry):
        """Registry includes the list_projects tool."""
        tool = registry.get("list_projects")
        assert tool is not None
        assert tool.name == "list_projects"
        assert callable(tool.handler)

    def test_registry_includes_create_project(self, registry):
        """Registry includes the create_project tool."""
        tool = registry.get("create_project")
        assert tool is not None
        assert tool.name == "create_project"
        assert callable(tool.handler)

    def test_all_three_tools_accessible_via_dispatch(self, registry, tool_context):
        """All three tools can be looked up via dispatch (unknown checks pass)."""
        assert registry.get("generate_media") is not None
        assert registry.get("list_projects") is not None
        assert registry.get("create_project") is not None

        tool_names = list(registry.list_all().keys())
        assert "generate_media" in tool_names
        assert "list_projects" in tool_names
        assert "create_project" in tool_names
