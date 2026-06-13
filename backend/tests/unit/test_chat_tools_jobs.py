"""Tests for chatbot job lifecycle tools that route through call_user_api."""

from unittest.mock import AsyncMock, patch

import pytest

from app.chatbot.tools import (
    ToolContext,
    _handle_batch_create_jobs,
    _handle_create_job,
    _handle_delete_job,
    _handle_download_job,
    _handle_get_job_status,
    _handle_list_user_jobs,
    _handle_retry_job,
    _handle_start_job,
    _handle_update_job,
    create_builtin_registry,
)


@pytest.fixture
def ctx():
    return ToolContext(user_id="test-user-id")


class TestToolRegistration:
    def test_all_job_tools_registered(self):
        registry = create_builtin_registry()
        names = registry.list_all().keys()
        expected = {
            "create_job",
            "get_job_status",
            "list_user_jobs",
            "start_job",
            "retry_job",
            "delete_job",
            "update_job",
            "download_job",
            "batch_create_jobs",
        }
        assert expected.issubset(names)


class TestCreateJob:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"job_id": "abc", "status": "pending"}
            result = await _handle_create_job(ctx, {"template": "tmpl-1", "prompt": "hello"})
            assert result == {"job_id": "abc", "status": "pending"}
            mock.assert_awaited_once()
            assert mock.call_args[0][1] == "POST"
            assert mock.call_args[0][2] == "/jobs"
            assert mock.call_args[1]["json_data"]["auto_start"] is True

    @pytest.mark.asyncio
    async def test_missing_template(self, ctx):
        result = await _handle_create_job(ctx, {"prompt": "hello"})
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_resolves_template_name_to_id(self):
        from unittest.mock import AsyncMock, MagicMock
        from uuid import uuid4

        template_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = template_id
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        ctx_with_db = ToolContext(user_id="test-user-id", db=db)

        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"job_id": "abc", "status": "pending"}
            result = await _handle_create_job(
                ctx_with_db,
                {"template": "prompt to video", "prompt": "hello"},
            )
            assert result == {"job_id": "abc", "status": "pending"}
            payload = mock.call_args[1]["json_data"]
            assert payload["template_id"] == str(template_id)

    @pytest.mark.asyncio
    async def test_maps_duration_and_avatars_to_api_schema(self, ctx):
        from uuid import uuid4

        avatar_id = uuid4()
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"job_id": "abc", "status": "pending"}
            result = await _handle_create_job(
                ctx,
                {
                    "template": "tmpl-1",
                    "prompt": "hello",
                    "duration": 60,
                    "avatars": [str(avatar_id)],
                },
            )
            assert result["job_id"] == "abc"
            payload = mock.call_args[1]["json_data"]
            assert payload["input_data"]["duration"] == 60
            assert payload["input_data"]["avatars"] == [{"avatar_id": str(avatar_id)}]

    @pytest.mark.asyncio
    async def test_legacy_duration_seconds_still_works(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"job_id": "abc", "status": "pending"}
            await _handle_create_job(
                ctx,
                {"template": "tmpl-1", "prompt": "hello", "duration_seconds": 45},
            )
            payload = mock.call_args[1]["json_data"]
            assert payload["input_data"]["duration"] == 45

    @pytest.mark.asyncio
    async def test_reference_image_url_is_not_forwarded(self, ctx):
        """reference_image_url is not part of the jobs API input schema."""
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"job_id": "abc", "status": "pending"}
            await _handle_create_job(
                ctx,
                {
                    "template": "tmpl-1",
                    "prompt": "hello",
                    "reference_image_url": "http://example.com/image.png",
                },
            )
            payload = mock.call_args[1]["json_data"]
            assert "reference_image_url" not in payload["input_data"]

    @pytest.mark.asyncio
    async def test_legacy_reference_image_id_converted_to_avatar(self, ctx):
        from uuid import uuid4

        avatar_id = uuid4()
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"job_id": "abc", "status": "pending"}
            await _handle_create_job(
                ctx,
                {
                    "template": "tmpl-1",
                    "prompt": "hello",
                    "reference_image_id": str(avatar_id),
                },
            )
            payload = mock.call_args[1]["json_data"]
            assert payload["input_data"]["avatars"] == [{"avatar_id": str(avatar_id)}]


class TestGetJobStatus:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "processing"}
            result = await _handle_get_job_status(ctx, {"job_id": "j1"})
            assert result == {"status": "processing"}
            mock.assert_awaited_once_with(ctx, "GET", "/jobs/j1")

    @pytest.mark.asyncio
    async def test_missing_job_id(self, ctx):
        result = await _handle_get_job_status(ctx, {})
        assert result["error"] == "missing_argument"


class TestListUserJobs:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"jobs": [], "count": 0}
            result = await _handle_list_user_jobs(ctx, {})
            assert result == {"jobs": [], "count": 0}
            mock.assert_awaited_once_with(ctx, "GET", "/jobs", params={})

    @pytest.mark.asyncio
    async def test_with_status_filter(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"jobs": [], "count": 0}
            result = await _handle_list_user_jobs(ctx, {"status": "pending", "limit": 5})
            assert result == {"jobs": [], "count": 0}
            mock.assert_awaited_once_with(
                ctx, "GET", "/jobs", params={"status": "pending", "limit": 5}
            )


class TestStartJob:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "started"}
            result = await _handle_start_job(ctx, {"job_id": "j1"})
            assert result == {"status": "started"}
            mock.assert_awaited_once_with(ctx, "POST", "/jobs/j1/start")

    @pytest.mark.asyncio
    async def test_missing_job_id(self, ctx):
        result = await _handle_start_job(ctx, {})
        assert result["error"] == "missing_argument"


class TestRetryJob:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "pending"}
            result = await _handle_retry_job(ctx, {"job_id": "j1"})
            assert result == {"status": "pending"}
            mock.assert_awaited_once_with(ctx, "POST", "/jobs/j1/retry")

    @pytest.mark.asyncio
    async def test_missing_job_id(self, ctx):
        result = await _handle_retry_job(ctx, {})
        assert result["error"] == "missing_argument"


class TestDeleteJob:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "deleted"}
            result = await _handle_delete_job(ctx, {"job_id": "j1"})
            assert result == {"status": "deleted"}
            mock.assert_awaited_once_with(ctx, "DELETE", "/jobs/j1")

    @pytest.mark.asyncio
    async def test_missing_job_id(self, ctx):
        result = await _handle_delete_job(ctx, {})
        assert result["error"] == "missing_argument"


class TestUpdateJob:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "pending"}
            result = await _handle_update_job(
                ctx, {"job_id": "j1", "input_data": {"style": "cinematic"}}
            )
            assert result == {"status": "pending"}
            mock.assert_awaited_once()
            assert mock.call_args[0][1] == "PATCH"
            assert mock.call_args[0][2] == "/jobs/j1"

    @pytest.mark.asyncio
    async def test_missing_job_id(self, ctx):
        result = await _handle_update_job(ctx, {"input_data": {}})
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_no_fields(self, ctx):
        result = await _handle_update_job(ctx, {"job_id": "j1"})
        assert result["error"] == "missing_argument"


class TestDownloadJob:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"token": "tok123"}
            result = await _handle_download_job(ctx, {"job_id": "j1"})
            assert result["download_url"] == "/api/jobs/j1/download"
            mock.assert_awaited_once_with(ctx, "GET", "/jobs/j1/download")

    @pytest.mark.asyncio
    async def test_error_from_api(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"error": "404", "message": "Not found"}
            result = await _handle_download_job(ctx, {"job_id": "j1"})
            assert result["error"] == "404"

    @pytest.mark.asyncio
    async def test_missing_job_id(self, ctx):
        result = await _handle_download_job(ctx, {})
        assert result["error"] == "missing_argument"


class TestBatchCreateJobs:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"created_count": 2, "job_ids": ["a", "b"]}
            result = await _handle_batch_create_jobs(
                ctx,
                {"template_id": "tmpl-1", "jobs": [{"prompt": "p1"}, {"prompt": "p2"}]},
            )
            assert result == {"created_count": 2, "job_ids": ["a", "b"]}
            mock.assert_awaited_once()
            assert mock.call_args[0][1] == "POST"
            assert mock.call_args[0][2] == "/jobs/batch"

    @pytest.mark.asyncio
    async def test_missing_template_id(self, ctx):
        result = await _handle_batch_create_jobs(ctx, {"jobs": []})
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_missing_jobs(self, ctx):
        result = await _handle_batch_create_jobs(ctx, {"template_id": "tmpl-1"})
        assert result["error"] == "missing_argument"
