"""Tests for posting a chat completion card when a job completes."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import Conversation, Job, Message
from app.workers.tasks import _post_completion_message


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
        title="Test Video",
        input_data={"prompt": "test"},
        chat_conversation_id=conversation.id,
        chat_message_id=uuid4(),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_completion_creates_job_completed_card(db_session, chat_job, conversation):
    chat_job.output_path = "output/test.mp4"
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        with patch(
            "app.services.job_chat_notifier.get_storage_backend"
        ) as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(
                return_value="/api/uploads/stream/output/test.mp4"
            )
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
    assert "is ready" in message.content

    attachment = message.attachments[0]
    assert attachment["kind"] == "job_card"
    assert attachment["card_type"] == "job_completed"
    assert attachment["job_id"] == str(chat_job.id)
    assert attachment["actions"] == ["download"]
    assert attachment["data"]["output_url"] == "/api/uploads/stream/output/test.mp4"
    assert message.job_id == chat_job.id


@pytest.mark.asyncio
async def test_completion_does_not_duplicate_message(db_session, chat_job, conversation):
    chat_job.output_path = "output/test.mp4"
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        with patch(
            "app.services.job_chat_notifier.get_storage_backend"
        ) as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(
                return_value="/api/uploads/stream/output/test.mp4"
            )
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
async def test_completion_posts_card_with_preview_when_no_output(
    db_session, chat_job, conversation
):
    chat_job.preview_path = "previews/test.png"
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ):
        with patch(
            "app.services.job_chat_notifier.get_storage_backend"
        ) as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(
                side_effect=lambda path: f"/api/uploads/stream/{path}"
            )
            await _post_completion_message(chat_job.id, db=db_session)

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.job_id == chat_job.id,
        )
    )
    message = result.scalar_one()
    attachment = message.attachments[0]
    assert attachment["card_type"] == "job_completed"
    assert attachment["data"]["output_url"] is None
    assert attachment["data"]["preview_url"] == "/api/uploads/stream/previews/test.png"


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

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        await _post_completion_message(job.id, db=db_session)

    mock_ws.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_posts_card_even_when_no_media_path(
    db_session, chat_job, conversation
):
    chat_job.output_path = None
    chat_job.preview_path = None
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        await _post_completion_message(chat_job.id, db=db_session)

    mock_ws.assert_awaited_once()
    result = await db_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    message = result.scalar_one()
    assert message.attachments[0]["card_type"] == "job_completed"
    assert message.attachments[0]["data"]["output_url"] is None
    assert message.attachments[0]["data"]["preview_url"] is None


@pytest.mark.asyncio
async def test_completion_guard_ignores_intermediate_cards(
    db_session, chat_job, conversation
):
    """A pre-existing scene_plan card must not block the job_completed card,
    and calling completion twice must not create duplicate job_completed cards."""
    chat_job.output_path = "output/test.mp4"
    await db_session.commit()

    # Pre-seed an intermediate stage card.
    intermediate = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Planned 1 scene for testing.",
        job_id=chat_job.id,
        attachments=[
            {
                "kind": "job_card",
                "card_type": "scene_plan",
                "job_id": str(chat_job.id),
                "title": "Scene plan",
                "data": {"scenes": []},
                "actions": ["generate_images"],
            }
        ],
    )
    db_session.add(intermediate)
    await db_session.commit()

    with patch(
        "app.services.job_chat_notifier.ws_manager.broadcast_chat_message",
        new_callable=AsyncMock,
    ) as mock_ws:
        with patch(
            "app.services.job_chat_notifier.get_storage_backend"
        ) as mock_storage:
            mock_storage.return_value.get_url = AsyncMock(
                return_value="/api/uploads/stream/output/test.mp4"
            )
            await _post_completion_message(chat_job.id, db=db_session)
            await _post_completion_message(chat_job.id, db=db_session)

    assert mock_ws.await_count == 1

    result = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.job_id == chat_job.id,
        )
    )
    messages = [
        msg for msg in result.scalars().all() if msg.attachments is not None
    ]
    completed_cards = [
        msg
        for msg in messages
        if any(
            attachment.get("card_type") == "job_completed"
            for attachment in (msg.attachments or [])
        )
    ]
    assert len(completed_cards) == 1
    assert any(
        attachment.get("card_type") == "scene_plan"
        for msg in messages
        for attachment in (msg.attachments or [])
    )
