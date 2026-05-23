"""Tests for built-in chatbot tool handlers."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.chatbot.tools import (
    ToolContext,
    ToolRegistry,
    create_builtin_registry,
    dispatch,
)
from app.database import Job, Style, Template, UserSettings
from app.models.media import MediaAsset


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


class TestCreateJob:
    """Tests for create_job tool."""

    @pytest.mark.asyncio
    async def test_happy_path(self, db_session, registry, tool_context, template):
        """create_job creates a Job row when auto_create_jobs is True."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "create_job",
            {
                "template": str(template.id),
                "prompt": "A cat playing piano",
                "style": "realistic",
                "duration_seconds": 10,
            },
            ctx,
            registry,
        )

        assert "error" not in result
        assert "job_id" in result
        assert result["status"] == "pending"
        assert "/api/jobs/" in result["monitor_url"]

        job_uuid = UUID(result["job_id"])
        job_result = await db_session.execute(select(Job).where(Job.id == job_uuid))
        job = job_result.scalar_one()
        assert job.user_id == UUID(ctx.user_id)
        assert job.template_id == template.id
        assert job.input_data["prompt"] == "A cat playing piano"

    @pytest.mark.asyncio
    async def test_missing_db_returns_error(self, registry, tool_context):
        """create_job without db returns error."""
        ctx = tool_context(db_session=None)
        result = await dispatch(
            "create_job",
            {"template": "t1", "prompt": "test"},
            ctx,
            registry,
        )
        assert result["error"] == "missing_db"

    @pytest.mark.asyncio
    async def test_missing_template_arg(self, db_session, registry, tool_context):
        """create_job without template returns validation error."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "create_job",
            {"prompt": "test"},
            ctx,
            registry,
        )
        assert result["error"] == "missing_argument"
        assert "template" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_prompt_arg(self, db_session, registry, tool_context):
        """create_job without prompt returns validation error."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "create_job",
            {"template": "t1"},
            ctx,
            registry,
        )
        assert result["error"] == "missing_argument"
        assert "prompt" in result["message"]

    @pytest.mark.asyncio
    async def test_template_not_found(self, db_session, registry, tool_context):
        """create_job with unknown template returns not_found."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "create_job",
            {"template": "nonexistent-template", "prompt": "test"},
            ctx,
            registry,
        )
        assert result["error"] == "not_found"

    @pytest.mark.asyncio
    async def test_auto_create_jobs_false_returns_draft(
        self, db_session, registry, tool_context, template
    ):
        """When auto_create_jobs is False, returns draft payload."""
        settings = UserSettings(
            user_id=UUID(tool_context(db_session).user_id),
            preferences={"auto_create_jobs": False},
        )
        db_session.add(settings)
        await db_session.commit()

        ctx = tool_context(db_session)
        result = await dispatch(
            "create_job",
            {"template": str(template.id), "prompt": "test prompt"},
            ctx,
            registry,
        )

        assert result["action"] == "draft"
        assert "payload" in result
        assert result["payload"]["template_id"] == str(template.id)

    @pytest.mark.asyncio
    async def test_user_scoping_other_user_cannot_access(
        self, db_session, registry, tool_context, template
    ):
        """A job created by user A should not be queryable by user B via get_job_status."""
        from app.database import User
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            hashed_password=pwd_context.hash("pass"),
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.commit()

        ctx_a = tool_context(db_session)
        result = await dispatch(
            "create_job",
            {"template": str(template.id), "prompt": "scoped"},
            ctx_a,
            registry,
        )
        job_id = result["job_id"]

        ctx_b = ToolContext(user_id=str(other_user.id), db=db_session)
        status_result = await dispatch(
            "get_job_status",
            {"job_id": job_id},
            ctx_b,
            registry,
        )
        assert status_result["error"] == "not_found"


class TestListTemplates:
    """Tests for list_templates tool."""

    @pytest.mark.asyncio
    async def test_returns_plugins(self, registry, tool_context):
        """list_templates returns available plugins."""
        ctx = tool_context()
        result = await dispatch("list_templates", {}, ctx, registry)
        assert "templates" in result
        assert isinstance(result["templates"], list)


class TestListStyles:
    """Tests for list_styles tool."""

    @pytest.mark.asyncio
    async def test_happy_path(self, db_session, registry, tool_context):
        """list_styles returns styles from DB."""
        style = Style(name="Cinematic", category="video", params={})
        db_session.add(style)
        await db_session.commit()

        ctx = tool_context(db_session)
        result = await dispatch("list_styles", {}, ctx, registry)
        assert "error" not in result
        assert len(result["styles"]) >= 1
        assert result["styles"][0]["name"] == "Cinematic"

    @pytest.mark.asyncio
    async def test_missing_db(self, registry, tool_context):
        """list_styles without db returns error."""
        ctx = tool_context()
        result = await dispatch("list_styles", {}, ctx, registry)
        assert result["error"] == "missing_db"


class TestListModels:
    """Tests for list_models tool."""

    @pytest.mark.asyncio
    async def test_all_modalities(self, registry, tool_context):
        """list_models without modality returns all model types."""
        ctx = tool_context()
        result = await dispatch("list_models", {}, ctx, registry)
        assert "image_models" in result
        assert "video_models" in result
        assert "text_models" in result

    @pytest.mark.asyncio
    async def test_filter_by_modality(self, registry, tool_context):
        """list_models with modality filter returns only that type."""
        ctx = tool_context()
        result = await dispatch("list_models", {"modality": "image"}, ctx, registry)
        assert result["modality"] == "image"
        assert "models" in result

    @pytest.mark.asyncio
    async def test_invalid_modality(self, registry, tool_context):
        """list_models with invalid modality returns error."""
        ctx = tool_context()
        result = await dispatch("list_models", {"modality": "audio"}, ctx, registry)
        assert result["error"] == "invalid_modality"


class TestGetJobStatus:
    """Tests for get_job_status tool."""

    @pytest.mark.asyncio
    async def test_happy_path(self, db_session, registry, tool_context, job_for_user):
        """get_job_status returns job details for the owner."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "get_job_status",
            {"job_id": str(job_for_user.id)},
            ctx,
            registry,
        )
        assert "error" not in result
        assert result["job_id"] == str(job_for_user.id)
        assert result["status"] == job_for_user.status

    @pytest.mark.asyncio
    async def test_missing_job_id(self, db_session, registry, tool_context):
        """get_job_status without job_id returns error."""
        ctx = tool_context(db_session)
        result = await dispatch("get_job_status", {}, ctx, registry)
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_invalid_job_id(self, db_session, registry, tool_context):
        """get_job_status with invalid UUID returns error."""
        ctx = tool_context(db_session)
        result = await dispatch("get_job_status", {"job_id": "not-a-uuid"}, ctx, registry)
        assert result["error"] == "invalid_argument"

    @pytest.mark.asyncio
    async def test_not_found(self, db_session, registry, tool_context):
        """get_job_status for non-existent job returns not_found."""
        ctx = tool_context(db_session)
        result = await dispatch(
            "get_job_status",
            {"job_id": str(uuid4())},
            ctx,
            registry,
        )
        assert result["error"] == "not_found"


class TestListUserJobs:
    """Tests for list_user_jobs tool."""

    @pytest.mark.asyncio
    async def test_happy_path(self, db_session, registry, tool_context, job_for_user):
        """list_user_jobs returns jobs scoped to the user."""
        ctx = tool_context(db_session)
        result = await dispatch("list_user_jobs", {}, ctx, registry)
        assert "error" not in result
        assert result["count"] >= 1
        job_ids = {j["job_id"] for j in result["jobs"]}
        assert str(job_for_user.id) in job_ids

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db_session, registry, tool_context, job_for_user):
        """list_user_jobs respects status filter."""
        ctx = tool_context(db_session)
        result = await dispatch("list_user_jobs", {"status": "pending"}, ctx, registry)
        assert all(j["status"] == "pending" for j in result["jobs"])

    @pytest.mark.asyncio
    async def test_missing_db(self, registry, tool_context):
        """list_user_jobs without db returns error."""
        ctx = tool_context()
        result = await dispatch("list_user_jobs", {}, ctx, registry)
        assert result["error"] == "missing_db"


class TestSearchMediaLibrary:
    """Tests for search_media_library tool."""

    @pytest.mark.asyncio
    async def test_happy_path(self, db_session, registry, tool_context, regular_user):
        """search_media_library returns matching assets."""
        asset = MediaAsset(
            user_id=regular_user.id,
            name="sunset_clip.mp4",
            file_path="/media/sunset_clip.mp4",
            file_type="video",
            source_type="generated",
        )
        db_session.add(asset)
        await db_session.commit()

        ctx = tool_context(db_session)
        result = await dispatch(
            "search_media_library",
            {"query": "sunset"},
            ctx,
            registry,
        )
        assert "error" not in result
        assert result["count"] >= 1
        assert any("sunset" in a["name"] for a in result["assets"])

    @pytest.mark.asyncio
    async def test_filter_by_file_type(self, db_session, registry, tool_context, regular_user):
        """search_media_library respects file_type filter."""
        img = MediaAsset(
            user_id=regular_user.id,
            name="photo.jpg",
            file_path="/media/photo.jpg",
            file_type="image",
            source_type="uploaded",
        )
        db_session.add(img)
        await db_session.commit()

        ctx = tool_context(db_session)
        result = await dispatch(
            "search_media_library",
            {"query": "photo", "file_type": "image"},
            ctx,
            registry,
        )
        assert all(a["file_type"] == "image" for a in result["assets"])

    @pytest.mark.asyncio
    async def test_missing_query(self, db_session, registry, tool_context):
        """search_media_library without query returns error."""
        ctx = tool_context(db_session)
        result = await dispatch("search_media_library", {}, ctx, registry)
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_missing_db(self, registry, tool_context):
        """search_media_library without db returns error."""
        ctx = tool_context()
        result = await dispatch("search_media_library", {"query": "x"}, ctx, registry)
        assert result["error"] == "missing_db"


class TestEnhancePrompt:
    """Tests for enhance_prompt tool."""

    @pytest.mark.asyncio
    async def test_missing_prompt(self, registry, tool_context):
        """enhance_prompt without prompt returns error."""
        ctx = tool_context()
        result = await dispatch("enhance_prompt", {}, ctx, registry)
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_enhance_prompt_calls_llm(self, registry, tool_context, mocker):
        """enhance_prompt calls LLMClient.generate and returns enhanced prompt."""
        ctx = tool_context()
        mock_generate = mocker.patch(
            "app.chatbot.tools.LLMClient.generate",
            return_value="A majestic cat playing a grand piano in a sunlit room",
        )
        mock_close = mocker.patch("app.chatbot.tools.LLMClient.close")

        result = await dispatch(
            "enhance_prompt",
            {"prompt": "cat playing piano", "target": "video"},
            ctx,
            registry,
        )

        mock_generate.assert_awaited_once()
        mock_close.assert_awaited_once()
        assert result["original_prompt"] == "cat playing piano"
        assert "enhanced_prompt" in result


class TestEstimateJobCost:
    """Tests for estimate_job_cost tool."""

    @pytest.mark.asyncio
    async def test_happy_path(self, registry, tool_context):
        """estimate_job_cost returns cost breakdown."""
        ctx = tool_context()
        result = await dispatch(
            "estimate_job_cost",
            {
                "template": "music_video",
                "image_model": "flux1-schnell",
                "video_model": "wan2.2",
                "duration_seconds": 15,
            },
            ctx,
            registry,
        )
        assert "error" not in result
        assert result["estimated_clips"] == 3
        assert result["estimated_cost"] > 0
        assert result["currency"] == "credits"

    @pytest.mark.asyncio
    async def test_missing_duration(self, registry, tool_context):
        """estimate_job_cost without duration_seconds returns error."""
        ctx = tool_context()
        result = await dispatch("estimate_job_cost", {}, ctx, registry)
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_defaults_for_unknown_models(self, registry, tool_context):
        """estimate_job_cost uses default costs for unknown models."""
        ctx = tool_context()
        result = await dispatch(
            "estimate_job_cost",
            {"duration_seconds": 5},
            ctx,
            registry,
        )
        assert "error" not in result
        assert result["estimated_cost"] > 0
