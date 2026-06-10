"""Tests for per-plugin input_data Pydantic validation (T28)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.database import Job, Template
from app.plugins.registry import discover_plugins


class TestJobInputValidation:
    """Validation of job.input_data against per-plugin Pydantic schemas."""

    @pytest.fixture(autouse=True, scope="class")
    def _discover_plugins(self):
        discover_plugins()

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.zrange = AsyncMock(return_value=[])
        pipe = MagicMock()
        pipe.zremrangebyscore = MagicMock(return_value=None)
        pipe.zcard = MagicMock(return_value=None)
        pipe.zadd = MagicMock(return_value=None)
        pipe.expire = MagicMock(return_value=None)
        pipe.execute = AsyncMock(return_value=[None, 0])
        redis.pipeline = MagicMock(return_value=pipe)
        return redis

    @pytest.fixture
    async def music_video_template(self, db_session):
        template = Template(
            id=uuid4(),
            name="Music Video",
            description="A music video template",
            config={"plugin_id": "music_video", "workflow_type": "scene_based"},
            is_builtin=True,
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)
        return template

    @pytest.fixture
    async def prompt_to_video_template(self, db_session):
        template = Template(
            id=uuid4(),
            name="Prompt to Video",
            description="A prompt-to-video template",
            config={"plugin_id": "prompt_to_video", "workflow_type": "scene_based"},
            is_builtin=True,
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)
        return template

    @pytest.fixture
    async def script_to_video_template(self, db_session):
        template = Template(
            id=uuid4(),
            name="Script to Video",
            description="A script-to-video template",
            config={"plugin_id": "script_to_video", "workflow_type": "scene_based"},
            is_builtin=True,
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)
        return template

    # ------------------------------------------------------------------
    # Music Video
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_music_video_unknown_field_returns_422(
        self,
        client: AsyncClient,
        regular_user_token: str,
        music_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            with patch("app.api.jobs.process_scene_video_job.delay"):
                response = await client.post(
                    "/api/jobs",
                    json={
                        "template_id": str(music_video_template.id),
                        "input_data": {
                            "audio_file": "song.mp3",
                            "style": "cinematic",
                            "bogus_field": 123,
                        },
                        "auto_start": False,
                    },
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                )
        assert response.status_code == 422
        detail = response.json().get("detail", {})
        errors = detail if isinstance(detail, list) else detail.get("errors", [])
        assert any("bogus_field" in str(e) for e in errors)

    @pytest.mark.asyncio
    async def test_music_video_valid_payload_returns_201(
        self,
        client: AsyncClient,
        regular_user_token: str,
        music_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            with patch("app.api.jobs.process_scene_video_job.delay"):
                response = await client.post(
                    "/api/jobs",
                    json={
                        "template_id": str(music_video_template.id),
                        "input_data": {
                            "audio_file": "song.mp3",
                            "style": "cinematic",
                            "aspect_ratio": "16:9",
                        },
                        "auto_start": False,
                    },
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["input_data"]["audio_file"] == "song.mp3"

    @pytest.mark.asyncio
    async def test_music_video_missing_required_field_returns_422(
        self,
        client: AsyncClient,
        regular_user_token: str,
        music_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            with patch("app.api.jobs.process_scene_video_job.delay"):
                response = await client.post(
                    "/api/jobs",
                    json={
                        "template_id": str(music_video_template.id),
                        "input_data": {"style": "cinematic"},
                        "auto_start": False,
                    },
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                )
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # Prompt to Video
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_prompt_to_video_valid_payload(
        self,
        client: AsyncClient,
        regular_user_token: str,
        prompt_to_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            with patch("app.api.jobs.process_scene_video_job.delay"):
                response = await client.post(
                    "/api/jobs",
                    json={
                        "template_id": str(prompt_to_video_template.id),
                        "input_data": {
                            "prompt": "A cat playing piano",
                            "style": "anime",
                            "duration": 30,
                            "aspect_ratio": "9:16",
                            "fps": 24,
                            "generate_audio": True,
                        },
                        "auto_start": False,
                    },
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert data["input_data"]["prompt"] == "A cat playing piano"

    @pytest.mark.asyncio
    async def test_prompt_to_video_invalid_style_returns_422(
        self,
        client: AsyncClient,
        regular_user_token: str,
        prompt_to_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/jobs",
                json={
                    "template_id": str(prompt_to_video_template.id),
                    "input_data": {
                        "prompt": "A cat playing piano",
                        "style": "watercolor",
                    },
                    "auto_start": False,
                },
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # Script to Video
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_script_to_video_valid_payload(
        self,
        client: AsyncClient,
        regular_user_token: str,
        script_to_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            with patch("app.api.jobs.process_scene_video_job.delay"):
                response = await client.post(
                    "/api/jobs",
                    json={
                        "template_id": str(script_to_video_template.id),
                        "input_data": {
                            "script": "Welcome to our channel. [Show a sunset] Today we explore...",
                            "style": "realistic",
                            "voice": "female",
                            "aspect_ratio": "16:9",
                            "background_music": True,
                        },
                        "auto_start": False,
                    },
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert data["input_data"]["script"].startswith("Welcome")

    @pytest.mark.asyncio
    async def test_script_to_video_missing_script_returns_422(
        self,
        client: AsyncClient,
        regular_user_token: str,
        script_to_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/jobs",
                json={
                    "template_id": str(script_to_video_template.id),
                    "input_data": {"style": "realistic"},
                    "auto_start": False,
                },
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # Plugin without schema (legacy / permissive)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_plugin_without_schema_still_accepted(
        self,
        client: AsyncClient,
        regular_user_token: str,
        template: Template,
        mock_redis,
    ):
        """Templates whose plugin has no get_input_schema() remain permissive."""
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            with patch("app.api.jobs.process_video_job.delay"):
                response = await client.post(
                    "/api/jobs",
                    json={
                        "template_id": str(template.id),
                        "input_data": {"anything": "goes", "nested": {"key": 1}},
                        "auto_start": False,
                    },
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert data["input_data"]["anything"] == "goes"

    # ------------------------------------------------------------------
    # Batch create
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_batch_job_validates_input_data(
        self,
        client: AsyncClient,
        regular_user_token: str,
        music_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/jobs/batch",
                json={
                    "template_id": str(music_video_template.id),
                    "jobs": [
                        {"audio_file": "a.mp3", "style": "cinematic"},
                        {"audio_file": "b.mp3", "style": "anime", "bogus": 1},
                    ],
                    "auto_start": False,
                },
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
        assert response.status_code == 422
        detail = response.json().get("detail", {})
        errors = detail if isinstance(detail, list) else detail.get("errors", [])
        assert any("bogus" in str(e) for e in errors)

    @pytest.mark.asyncio
    async def test_batch_job_valid_payload_passes(
        self,
        client: AsyncClient,
        regular_user_token: str,
        music_video_template: Template,
        mock_redis,
    ):
        with patch("app.dependencies.rate_limit.get_redis", return_value=mock_redis):
            response = await client.post(
                "/api/jobs/batch",
                json={
                    "template_id": str(music_video_template.id),
                    "jobs": [
                        {"audio_file": "a.mp3", "style": "cinematic"},
                        {"audio_file": "b.mp3", "style": "anime"},
                    ],
                    "auto_start": False,
                },
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["created_count"] == 2
