"""Tests for chatbot scene tools that route through call_user_api."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.chatbot.tools import (
    ToolContext,
    _handle_add_scene,
    _handle_delete_scene,
    _handle_export_job,
    _handle_extract_lyrics,
    _handle_generate_all_images,
    _handle_generate_all_videos,
    _handle_generate_scene_image,
    _handle_generate_scene_video,
    _handle_get_audio_metadata,
    _handle_get_export_options,
    _handle_list_scenes,
    _handle_plan_scenes,
    _handle_regenerate_all_scenes,
    _handle_regenerate_prompts,
    _handle_reorder_scenes,
    _handle_set_job_stage,
    _handle_set_manual_lyrics,
    _handle_update_lyrics,
    _handle_update_scene,
    create_builtin_registry,
)


@pytest.fixture
def ctx():
    return ToolContext(user_id=str(uuid4()), db=None, request_id="")


@pytest.fixture
def job_id():
    return str(uuid4())


@pytest.fixture
def scene_id():
    return str(uuid4())


def test_all_scene_tools_registered():
    registry = create_builtin_registry()
    names = {
        "get_audio_metadata",
        "extract_lyrics",
        "set_manual_lyrics",
        "update_lyrics",
        "plan_scenes",
        "list_scenes",
        "add_scene",
        "update_scene",
        "delete_scene",
        "reorder_scenes",
        "set_job_stage",
        "regenerate_prompts",
        "generate_scene_image",
        "generate_scene_video",
        "regenerate_all_scenes",
        "generate_all_images",
        "generate_all_videos",
        "export_job",
        "get_export_options",
    }
    for name in names:
        assert registry.get(name) is not None, f"{name} not registered"
    assert len(names) == 19


@pytest.mark.asyncio
async def test_extract_lyrics(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"lyrics": "line1\nline2"}
        result = await _handle_extract_lyrics(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(
            ctx, "POST", f"/jobs/{job_id}/lyrics/extract", json_data={"audio_file_path": ""}
        )
        assert result["lyrics"] == "line1\nline2"


@pytest.mark.asyncio
async def test_set_manual_lyrics(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"lyrics": "hello world"}
        result = await _handle_set_manual_lyrics(
            ctx, {"job_id": job_id, "lyrics": "hello world", "duration": 120.0}
        )
        mock.assert_awaited_once_with(
            ctx,
            "POST",
            f"/jobs/{job_id}/lyrics/manual",
            json_data={"lyrics_text": "hello world", "duration": 120.0},
        )
        assert result["lyrics"] == "hello world"


@pytest.mark.asyncio
async def test_update_lyrics(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"lyrics": "updated"}
        result = await _handle_update_lyrics(
            ctx,
            {
                "job_id": job_id,
                "lyrics": "updated",
                "duration": 90.0,
                "replan": True,
                "style": "anime",
            },
        )
        mock.assert_awaited_once_with(
            ctx,
            "PUT",
            f"/jobs/{job_id}/lyrics",
            json_data={
                "lyrics_text": "updated",
                "duration": 90.0,
                "replan": True,
                "style": "anime",
            },
        )
        assert result["lyrics"] == "updated"


@pytest.mark.asyncio
async def test_plan_scenes(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"scenes": [{"scene_number": 1}], "summary": "ok"}
        result = await _handle_plan_scenes(
            ctx,
            {
                "job_id": job_id,
                "lyrics_data": {"lines": []},
                "duration": 120.0,
                "style": "realistic",
            },
        )
        mock.assert_awaited_once_with(
            ctx,
            "POST",
            f"/jobs/{job_id}/scenes/plan",
            json_data={"lyrics_data": {"lines": []}, "duration": 120.0, "style": "realistic"},
        )
        assert result["scenes"][0]["scene_number"] == 1


@pytest.mark.asyncio
async def test_list_scenes(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = [{"id": str(uuid4()), "scene_number": 1}]
        result = await _handle_list_scenes(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(ctx, "GET", f"/jobs/{job_id}/scenes")
        assert len(result) == 1


@pytest.mark.asyncio
async def test_add_scene(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": str(uuid4()), "scene_number": 2}
        result = await _handle_add_scene(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(ctx, "POST", f"/jobs/{job_id}/scenes")
        assert result["scene_number"] == 2


@pytest.mark.asyncio
async def test_update_scene(ctx, job_id, scene_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": scene_id, "mood": "happy"}
        result = await _handle_update_scene(
            ctx, {"job_id": job_id, "scene_id": scene_id, "mood": "happy"}
        )
        mock.assert_awaited_once_with(
            ctx,
            "PATCH",
            f"/jobs/{job_id}/scenes/{scene_id}",
            json_data={"mood": "happy"},
        )
        assert result["mood"] == "happy"


@pytest.mark.asyncio
async def test_delete_scene(ctx, job_id, scene_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "deleted"}
        result = await _handle_delete_scene(ctx, {"job_id": job_id, "scene_id": scene_id})
        mock.assert_awaited_once_with(
            ctx, "DELETE", f"/jobs/{job_id}/scenes/{scene_id}"
        )
        assert result["status"] == "deleted"


@pytest.mark.asyncio
async def test_reorder_scenes(ctx, job_id, scene_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "reordered"}
        result = await _handle_reorder_scenes(ctx, {"job_id": job_id, "order": [scene_id]})
        mock.assert_awaited_once_with(
            ctx, "POST", f"/jobs/{job_id}/scenes/reorder", json_data=[scene_id]
        )
        assert result["status"] == "reordered"


@pytest.mark.asyncio
async def test_set_job_stage(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"job_id": job_id, "stage": "planned"}
        result = await _handle_set_job_stage(ctx, {"job_id": job_id, "stage": "planned"})
        mock.assert_awaited_once_with(
            ctx, "PATCH", f"/jobs/{job_id}/stage", json_data={"stage": "planned"}
        )
        assert result["stage"] == "planned"


@pytest.mark.asyncio
async def test_generate_scene_image(ctx, job_id, scene_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "queued", "scene_id": scene_id, "media_type": "image"}
        result = await _handle_generate_scene_image(
            ctx, {"job_id": job_id, "scene_id": scene_id}
        )
        mock.assert_awaited_once_with(
            ctx, "POST", f"/jobs/{job_id}/scenes/generate-image/{scene_id}"
        )
        assert result["media_type"] == "image"


@pytest.mark.asyncio
async def test_generate_scene_video(ctx, job_id, scene_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "queued", "scene_id": scene_id, "media_type": "video"}
        result = await _handle_generate_scene_video(
            ctx, {"job_id": job_id, "scene_id": scene_id}
        )
        mock.assert_awaited_once_with(
            ctx, "POST", f"/jobs/{job_id}/scenes/generate-video/{scene_id}"
        )
        assert result["media_type"] == "video"


@pytest.mark.asyncio
async def test_regenerate_all_scenes(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "queued", "job_id": job_id, "scene_count": 3}
        result = await _handle_regenerate_all_scenes(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(ctx, "POST", f"/jobs/{job_id}/scenes/regenerate-all")
        assert result["scene_count"] == 3


@pytest.mark.asyncio
async def test_generate_all_images(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "queued", "job_id": job_id, "stage": "generating_images"}
        result = await _handle_generate_all_images(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(
            ctx, "POST", f"/jobs/{job_id}/scenes/generate-all-images"
        )
        assert result["stage"] == "generating_images"


@pytest.mark.asyncio
async def test_generate_all_videos(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "queued", "job_id": job_id, "stage": "generating_videos"}
        result = await _handle_generate_all_videos(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(
            ctx, "POST", f"/jobs/{job_id}/scenes/generate-all-videos"
        )
        assert result["stage"] == "generating_videos"


@pytest.mark.asyncio
async def test_regenerate_prompts(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"scenes": [{"id": str(uuid4()), "image_prompt": "new prompt"}]}
        result = await _handle_regenerate_prompts(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(
            ctx, "POST", f"/jobs/{job_id}/scenes/regenerate-prompts"
        )
        assert result["scenes"][0]["image_prompt"] == "new prompt"


@pytest.mark.asyncio
async def test_export_job(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "queued", "job_id": job_id, "stage": "rendering"}
        result = await _handle_export_job(
            ctx, {"job_id": job_id, "transition_type": "crossfade", "audio_volume": 0.9}
        )
        mock.assert_awaited_once_with(
            ctx,
            "POST",
            f"/jobs/{job_id}/export",
            json_data={"transition_type": "crossfade", "audio_volume": 0.9},
        )
        assert result["stage"] == "rendering"


@pytest.mark.asyncio
async def test_get_export_options(ctx, job_id):
    with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
        mock.return_value = {"job_id": job_id, "can_export": True, "total_scenes": 3}
        result = await _handle_get_export_options(ctx, {"job_id": job_id})
        mock.assert_awaited_once_with(ctx, "GET", f"/jobs/{job_id}/export-options")
        assert result["can_export"] is True


def test_maybe_truncate_lyrics_truncates_when_over_8kb():
    from app.chatbot.tools import _maybe_truncate_lyrics

    long_lyrics = "x" * (8 * 1024 + 100)
    payload = {"lyrics": long_lyrics}
    result = _maybe_truncate_lyrics(payload)
    assert result["lyrics"].endswith("\n...[truncated]")
    assert len(result["lyrics"].encode("utf-8")) <= 8 * 1024 + len("\n...[truncated]")


def test_maybe_truncate_lyrics_dict_form():
    from app.chatbot.tools import _maybe_truncate_lyrics

    long_text = "x" * (8 * 1024 + 50)
    payload = {"lyrics": {"full_text": long_text}}
    result = _maybe_truncate_lyrics(payload)
    assert result["lyrics"]["full_text"].endswith("\n...[truncated]")
