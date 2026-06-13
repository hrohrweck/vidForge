"""Tests for JobChatNotifier stage card posting."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import Conversation, Job, Message, VideoScene
from app.services.job_chat_notifier import JobChatNotifier


@pytest.fixture
async def chat_conversation(db_session, regular_user):
    conv = Conversation(
        user_id=regular_user.id,
        title="Test Chat",
        model_id="test-model",
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


@pytest.fixture
async def chat_job(db_session, regular_user, template, chat_conversation):
    job = Job(
        id=uuid4(),
        user_id=regular_user.id,
        template_id=template.id,
        status="processing",
        title="Test Video",
        input_data={"prompt": "test"},
        chat_conversation_id=chat_conversation.id,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.fixture
async def planned_scenes(db_session, chat_job):
    scenes = []
    for i in range(1, 3):
        scene = VideoScene(
            id=uuid4(),
            job_id=chat_job.id,
            scene_number=i,
            start_time=(i - 1) * 5.0,
            end_time=i * 5.0,
            visual_description=f"Scene {i}",
            image_prompt=f"Prompt {i}",
            mood="happy",
            camera_movement="pan",
        )
        db_session.add(scene)
        scenes.append(scene)
    await db_session.commit()
    return scenes


@pytest.fixture
async def scenes_with_thumbnails(db_session, chat_job):
    scenes = []
    for i in range(1, 3):
        scene = VideoScene(
            id=uuid4(),
            job_id=chat_job.id,
            scene_number=i,
            start_time=(i - 1) * 5.0,
            end_time=i * 5.0,
            visual_description=f"Scene {i}",
            thumbnail_path=f"thumbs/scene_{i}.png",
            status="image_ready",
        )
        db_session.add(scene)
        scenes.append(scene)
    await db_session.commit()
    return scenes


@pytest.fixture
async def scenes_with_videos(db_session, chat_job):
    scenes = []
    for i in range(1, 3):
        scene = VideoScene(
            id=uuid4(),
            job_id=chat_job.id,
            scene_number=i,
            start_time=(i - 1) * 5.0,
            end_time=i * 5.0,
            visual_description=f"Scene {i}",
            generated_video_path=f"videos/scene_{i}.mp4",
            status="video_ready",
        )
        db_session.add(scene)
        scenes.append(scene)
    await db_session.commit()
    return scenes


@pytest.mark.asyncio
async def test_notify_planned_posts_scene_plan_card(
    db_session, chat_job, planned_scenes
):
    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        await JobChatNotifier.notify_planned(db_session, chat_job)

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == chat_job.chat_conversation_id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    assert message.role == "assistant"
    assert "Planned 2 scene(s)" in message.content

    attachment = message.attachments[0]
    assert attachment["kind"] == "job_card"
    assert attachment["card_type"] == "scene_plan"
    assert attachment["job_id"] == str(chat_job.id)
    assert attachment["actions"] == ["generate_images"]
    assert len(attachment["data"]["scenes"]) == 2
    assert attachment["data"]["scenes"][0]["scene_number"] == 1

    mock_ws.assert_awaited_once_with(
        str(chat_job.chat_conversation_id), str(message.id)
    )


@pytest.mark.asyncio
async def test_notify_images_ready_posts_image_review_card(
    db_session, chat_job, scenes_with_thumbnails
):
    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        with patch(
            "app.services.job_chat_notifier.get_storage_backend"
        ) as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(
                side_effect=lambda path: f"http://localhost/{path}"
            )
            await JobChatNotifier.notify_images_ready(db_session, chat_job)

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == chat_job.chat_conversation_id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    attachment = message.attachments[0]
    assert attachment["card_type"] == "image_review"
    assert attachment["actions"] == ["generate_videos"]
    assert len(attachment["data"]["scenes"]) == 2
    assert attachment["data"]["scenes"][0]["thumbnail_url"] == (
        "http://localhost/thumbs/scene_1.png"
    )

    mock_ws.assert_awaited_once_with(
        str(chat_job.chat_conversation_id), str(message.id)
    )


@pytest.mark.asyncio
async def test_notify_videos_ready_posts_video_review_card(
    db_session, chat_job, scenes_with_videos
):
    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        with patch(
            "app.services.job_chat_notifier.get_storage_backend"
        ) as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(
                side_effect=lambda path: f"http://localhost/{path}"
            )
            await JobChatNotifier.notify_videos_ready(db_session, chat_job)

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == chat_job.chat_conversation_id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    attachment = message.attachments[0]
    assert attachment["card_type"] == "video_review"
    assert attachment["actions"] == ["export"]
    assert len(attachment["data"]["scenes"]) == 2
    assert attachment["data"]["scenes"][0]["preview_url"] == (
        "http://localhost/videos/scene_1.mp4"
    )

    mock_ws.assert_awaited_once_with(
        str(chat_job.chat_conversation_id), str(message.id)
    )


@pytest.mark.asyncio
async def test_notify_completed_posts_job_completed_card_even_when_autonomous(
    db_session, chat_job, chat_conversation
):
    chat_conversation.metadata_ = {"chat_autonomy": "autonomous"}
    chat_job.output_path = "output/final.mp4"
    chat_job.preview_path = "output/preview.mp4"
    chat_job.thumbnail_path = "output/thumb.jpg"
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        with patch(
            "app.services.job_chat_notifier.get_storage_backend"
        ) as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(
                side_effect=lambda path: f"http://localhost/{path}"
            )
            await JobChatNotifier.notify_completed(db_session, chat_job)

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == chat_job.chat_conversation_id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    attachment = message.attachments[0]
    assert attachment["card_type"] == "job_completed"
    assert attachment["actions"] == ["download"]
    assert attachment["data"]["output_url"] == "http://localhost/output/final.mp4"
    assert attachment["data"]["preview_url"] == "http://localhost/output/preview.mp4"
    assert attachment["data"]["thumbnail_url"] == (
        "http://localhost/output/thumb.jpg"
    )

    mock_ws.assert_awaited_once_with(
        str(chat_job.chat_conversation_id), str(message.id)
    )


@pytest.mark.asyncio
async def test_notify_failed_posts_job_error_card(
    db_session, chat_job
):
    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        await JobChatNotifier.notify_failed(db_session, chat_job, "it broke")

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == chat_job.chat_conversation_id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    attachment = message.attachments[0]
    assert attachment["card_type"] == "job_error"
    assert attachment["actions"] == ["retry", "cancel"]
    assert attachment["data"]["error_message"] == "it broke"

    mock_ws.assert_awaited_once_with(
        str(chat_job.chat_conversation_id), str(message.id)
    )


@pytest.mark.asyncio
async def test_intermediate_cards_skipped_when_autonomous(
    db_session, chat_job, chat_conversation, planned_scenes
):
    chat_conversation.metadata_ = {"chat_autonomy": "autonomous"}
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        await JobChatNotifier.notify_planned(db_session, chat_job)

    mock_ws.assert_not_awaited()
    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == chat_job.chat_conversation_id,
            Message.job_id == chat_job.id,
        )
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_no_card_when_no_chat_conversation_id(
    db_session, regular_user, template
):
    job = Job(
        id=uuid4(),
        user_id=regular_user.id,
        template_id=template.id,
        status="processing",
        title="No Chat Job",
        input_data={"prompt": "test"},
        chat_conversation_id=None,
    )
    db_session.add(job)
    await db_session.commit()

    scene = VideoScene(
        id=uuid4(),
        job_id=job.id,
        scene_number=1,
        start_time=0.0,
        end_time=5.0,
        visual_description="Scene",
    )
    db_session.add(scene)
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        await JobChatNotifier.notify_planned(db_session, job)
        await JobChatNotifier.notify_completed(db_session, job)

    mock_ws.assert_not_awaited()


@pytest.fixture
async def plugin_template(db_session):
    from app.database import Template

    tmpl = Template(
        id=uuid4(),
        name="Fake Plugin Template",
        description="A template for fake plugin tests",
        config={"plugin_id": "fake_plugin", "workflow_type": "scene_based"},
        is_builtin=True,
    )
    db_session.add(tmpl)
    await db_session.commit()
    await db_session.refresh(tmpl)
    return tmpl


@pytest.fixture
async def dispatch_chat_job(db_session, regular_user, plugin_template, chat_conversation):
    job = Job(
        id=uuid4(),
        user_id=regular_user.id,
        template_id=plugin_template.id,
        status="processing",
        title="Dispatch Test Video",
        input_data={"prompt": "test"},
        chat_conversation_id=chat_conversation.id,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


class _FakePlugin:
    plugin_id = "fake_plugin"

    async def enrich_inputs(self, db, job, context):
        return context

    async def plan_scenes(self, db, job, context):
        return context

    async def generate_images(self, db, job, scenes, context):
        return context

    async def generate_videos(self, db, job, scenes, context):
        return context

    async def render(self, db, job, scenes, context):
        return {"output_path": "output/final.mp4"}


@pytest.mark.asyncio
async def test_dispatch_generating_images_failure_posts_job_error_card(
    db_session, dispatch_chat_job, monkeypatch
):
    from app.workers import dispatcher as dispatcher_module

    monkeypatch.setattr(dispatcher_module.ctx, "_session_factory", lambda: db_session)
    monkeypatch.setattr(dispatcher_module, "get_plugin", lambda _pid: _FakePlugin())
    monkeypatch.setattr(dispatcher_module, "get_plugin_for_template", lambda _cfg: None)

    for i in range(1, 3):
        scene = VideoScene(
            id=uuid4(),
            job_id=dispatch_chat_job.id,
            scene_number=i,
            start_time=(i - 1) * 5.0,
            end_time=i * 5.0,
            visual_description=f"Scene {i}",
            status="failed",
        )
        db_session.add(scene)
    await db_session.commit()

    with patch.object(
        JobChatNotifier, "notify_failed", new_callable=AsyncMock
    ) as mock_notify_failed:
        result = await dispatcher_module.dispatch_stage(
            str(dispatch_chat_job.id), "generating_images"
        )

    assert result["status"] == "failed"
    assert result["stage"] == "generating_images"
    mock_notify_failed.assert_awaited_once()
    args = mock_notify_failed.call_args[0]
    assert args[0] is db_session
    assert str(args[1].id) == str(dispatch_chat_job.id)
    assert args[2] == "All image scenes failed to generate"


@pytest.mark.asyncio
async def test_dispatch_generating_videos_failure_posts_job_error_card(
    db_session, dispatch_chat_job, monkeypatch
):
    from app.workers import dispatcher as dispatcher_module

    monkeypatch.setattr(dispatcher_module.ctx, "_session_factory", lambda: db_session)
    monkeypatch.setattr(dispatcher_module, "get_plugin", lambda _pid: _FakePlugin())
    monkeypatch.setattr(dispatcher_module, "get_plugin_for_template", lambda _cfg: None)

    for i in range(1, 3):
        scene = VideoScene(
            id=uuid4(),
            job_id=dispatch_chat_job.id,
            scene_number=i,
            start_time=(i - 1) * 5.0,
            end_time=i * 5.0,
            visual_description=f"Scene {i}",
            status="failed",
        )
        db_session.add(scene)
    await db_session.commit()

    with patch.object(
        JobChatNotifier, "notify_failed", new_callable=AsyncMock
    ) as mock_notify_failed:
        result = await dispatcher_module.dispatch_stage(
            str(dispatch_chat_job.id), "generating_videos"
        )

    assert result["status"] == "failed"
    assert result["stage"] == "generating_videos"
    mock_notify_failed.assert_awaited_once()
    args = mock_notify_failed.call_args[0]
    assert args[0] is db_session
    assert str(args[1].id) == str(dispatch_chat_job.id)
    assert args[2] == "All video scenes failed to generate"
