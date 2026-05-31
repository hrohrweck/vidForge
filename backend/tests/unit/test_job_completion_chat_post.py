"""Tests for posting a chat message when a job completes."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import Conversation, Job, Message, User
from app.workers.tasks import _post_completion_message, update_job_status


@pytest.fixture
async def conversation(db_session, regular_user):
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
async def chat_job(db_session, regular_user, template, conversation):
    job = Job(
        id=uuid4(),
        user_id=regular_user.id,
        template_id=template.id,
        status="processing",
        input_data={"prompt": "test"},
        chat_conversation_id=conversation.id,
        chat_message_id=uuid4(),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_completion_creates_chat_message_with_media(db_session, chat_job, conversation):
    chat_job.output_path = "output/test.mp4"
    await db_session.commit()

    with patch("app.workers.tasks.ws_manager.broadcast_chat_message", new_callable=AsyncMock) as mock_ws:
        with patch("app.workers.tasks.get_storage_backend") as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(return_value="/api/uploads/stream/output/test.mp4")
            await _post_completion_message(chat_job.id, db=db_session)

    mock_ws.assert_awaited_once()
    assert mock_ws.call_args[0][0] == str(conversation.id)

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    assert message.role == "assistant"
    assert message.content == "Here is the result:"
    assert message.attachments == [
        {"kind": "video", "url": "/api/uploads/stream/output/test.mp4", "mime_type": "video/mp4"}
    ]
    assert message.job_id == chat_job.id


@pytest.mark.asyncio
async def test_completion_does_not_duplicate_message(db_session, chat_job, conversation):
    chat_job.output_path = "output/test.mp4"
    await db_session.commit()

    with patch("app.workers.tasks.ws_manager.broadcast_chat_message", new_callable=AsyncMock) as mock_ws:
        with patch("app.workers.tasks.get_storage_backend") as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(return_value="/api/uploads/stream/output/test.mp4")
            await _post_completion_message(chat_job.id, db=db_session)
            await _post_completion_message(chat_job.id, db=db_session)

    assert mock_ws.await_count == 1

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.job_id == chat_job.id,
        )
    )
    assert result.scalar_one_or_none() is not None
    count_result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.job_id == chat_job.id,
        )
    )
    assert len(list(count_result.scalars().all())) == 1


@pytest.mark.asyncio
async def test_completion_uses_preview_fallback(db_session, chat_job, conversation):
    chat_job.preview_path = "previews/test.png"
    await db_session.commit()

    with patch("app.workers.tasks.ws_manager.broadcast_chat_message", new_callable=AsyncMock):
        with patch("app.workers.tasks.get_storage_backend") as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(return_value="/api/uploads/stream/previews/test.png")
            await _post_completion_message(chat_job.id, db=db_session)

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    assert message.attachments == [
        {"kind": "image", "url": "/api/uploads/stream/previews/test.png", "mime_type": "image/png"}
    ]


@pytest.mark.asyncio
async def test_completion_skips_when_no_chat_link(db_session, regular_user, template):
    job = Job(
        id=uuid4(),
        user_id=regular_user.id,
        template_id=template.id,
        status="processing",
        input_data={"prompt": "test"},
        output_path="output/test.mp4",
    )
    db_session.add(job)
    await db_session.commit()

    with patch("app.workers.tasks.ws_manager.broadcast_chat_message", new_callable=AsyncMock) as mock_ws:
        await _post_completion_message(job.id, db=db_session)

    mock_ws.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_skips_when_no_media_path(db_session, chat_job, conversation):
    chat_job.output_path = None
    chat_job.preview_path = None
    await db_session.commit()

    with patch("app.workers.tasks.ws_manager.broadcast_chat_message", new_callable=AsyncMock) as mock_ws:
        await _post_completion_message(chat_job.id, db=db_session)

    mock_ws.assert_not_awaited()
    result = await db_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    assert result.scalar_one_or_none() is None
