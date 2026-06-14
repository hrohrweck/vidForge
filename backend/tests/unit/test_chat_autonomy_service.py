from uuid import uuid4

import pytest

from app.database import Conversation, User, UserSettings
from app.services.chat_autonomy_service import DEFAULT_MODE, ChatAutonomyService


@pytest.fixture
async def user_settings(db_session, regular_user: User):
    settings = UserSettings(user_id=regular_user.id)
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(settings)
    return settings


class TestChatAutonomyService:
    async def test_get_default_mode_returns_confirm_when_no_preference(
        self, db_session, regular_user: User
    ):
        mode = await ChatAutonomyService.get_default_mode(db_session, regular_user.id)
        assert mode == "confirm"

    async def test_get_default_mode_reads_user_preference(
        self, db_session, regular_user: User, user_settings: UserSettings
    ):
        user_settings.preferences = {"chat_autonomy": "autonomous"}
        await db_session.commit()

        mode = await ChatAutonomyService.get_default_mode(db_session, regular_user.id)
        assert mode == "autonomous"

    async def test_get_default_mode_invalid_value_falls_back(
        self, db_session, regular_user: User, user_settings: UserSettings
    ):
        user_settings.preferences = {"chat_autonomy": "unknown"}
        await db_session.commit()

        mode = await ChatAutonomyService.get_default_mode(db_session, regular_user.id)
        assert mode == DEFAULT_MODE

    async def test_get_mode_falls_back_to_default_when_metadata_unset(
        self, db_session, regular_user: User, conversation: Conversation
    ):
        mode = await ChatAutonomyService.get_mode(db_session, conversation.id, regular_user.id)
        assert mode == "confirm"

    async def test_get_mode_falls_back_to_user_preference(
        self, db_session, regular_user: User, conversation: Conversation, user_settings: UserSettings
    ):
        user_settings.preferences = {"chat_autonomy": "autonomous"}
        await db_session.commit()

        mode = await ChatAutonomyService.get_mode(db_session, conversation.id, regular_user.id)
        assert mode == "autonomous"

    async def test_set_mode_stores_override_and_get_mode_returns_it(
        self, db_session, regular_user: User, conversation: Conversation
    ):
        await ChatAutonomyService.set_mode(
            db_session, conversation.id, regular_user.id, "autonomous"
        )

        mode = await ChatAutonomyService.get_mode(db_session, conversation.id, regular_user.id)
        assert mode == "autonomous"

    async def test_set_mode_invalid_mode_raises_value_error(
        self, db_session, regular_user: User, conversation: Conversation
    ):
        with pytest.raises(ValueError):
            await ChatAutonomyService.set_mode(
                db_session, conversation.id, regular_user.id, "invalid"
            )

    async def test_set_mode_missing_conversation_raises_value_error(
        self, db_session, regular_user: User
    ):
        with pytest.raises(ValueError, match="Conversation not found"):
            await ChatAutonomyService.set_mode(
                db_session, uuid4(), regular_user.id, "autonomous"
            )

    async def test_set_mode_wrong_user_raises_value_error(
        self, db_session, conversation: Conversation
    ):
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.commit()

        with pytest.raises(ValueError, match="Conversation not found"):
            await ChatAutonomyService.set_mode(
                db_session, conversation.id, other_user.id, "autonomous"
            )

    async def test_get_mode_missing_conversation_raises_value_error(
        self, db_session, regular_user: User
    ):
        with pytest.raises(ValueError, match="Conversation not found"):
            await ChatAutonomyService.get_mode(db_session, uuid4(), regular_user.id)

    async def test_get_mode_wrong_user_raises_value_error(
        self, db_session, conversation: Conversation
    ):
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.commit()

        with pytest.raises(ValueError, match="Conversation not found"):
            await ChatAutonomyService.get_mode(
                db_session, conversation.id, other_user.id
            )
