import pytest
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select

from app.chatbot.service import ConversationService
from app.database import Conversation, Message, User


@pytest.fixture
async def svc(db_session):
    return ConversationService(db_session)


@pytest.fixture
async def other_user(db_session):
    user = User(
        id=uuid4(),
        email="other@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestCreate:
    async def test_create_conversation(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "Test Title", "gpt-4")
        assert conv.title == "Test Title"
        assert conv.model_id == "gpt-4"
        assert conv.user_id == regular_user.id
        assert conv.archived_at is None


class TestListForUser:
    async def test_lists_only_owned_conversations(self, svc, regular_user, other_user):
        c1 = await svc.create(regular_user.id, "Mine", "gpt-4")
        await svc.create(other_user.id, "Not Mine", "gpt-4")

        results = await svc.list_for_user(regular_user.id)
        assert len(results) == 1
        assert results[0].id == c1.id

    async def test_excludes_archived(self, svc, regular_user):
        c1 = await svc.create(regular_user.id, "Active", "gpt-4")
        c2 = await svc.create(regular_user.id, "Archived", "gpt-4")
        c2.archived_at = __import__("datetime").datetime.utcnow()
        await svc.db.commit()

        results = await svc.list_for_user(regular_user.id)
        assert len(results) == 1
        assert results[0].id == c1.id

    async def test_order_newest_first(self, svc, regular_user):
        c1 = await svc.create(regular_user.id, "First", "gpt-4")
        c2 = await svc.create(regular_user.id, "Second", "gpt-4")

        results = await svc.list_for_user(regular_user.id)
        assert [r.id for r in results] == [c2.id, c1.id]


class TestGet:
    async def test_get_owned_conversation(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "Mine", "gpt-4")
        fetched = await svc.get(regular_user.id, conv.id)
        assert fetched.id == conv.id

    async def test_get_nonexistent_returns_404(self, svc, regular_user):
        with pytest.raises(HTTPException) as exc:
            await svc.get(regular_user.id, uuid4())
        assert exc.value.status_code == 404

    async def test_get_other_users_returns_404(self, svc, regular_user, other_user):
        conv = await svc.create(other_user.id, "Not Mine", "gpt-4")
        with pytest.raises(HTTPException) as exc:
            await svc.get(regular_user.id, conv.id)
        assert exc.value.status_code == 404


class TestRename:
    async def test_rename_conversation(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "Old", "gpt-4")
        renamed = await svc.rename(regular_user.id, conv.id, "New")
        assert renamed.title == "New"

    async def test_rename_other_users_returns_404(self, svc, regular_user, other_user):
        conv = await svc.create(other_user.id, "Not Mine", "gpt-4")
        with pytest.raises(HTTPException) as exc:
            await svc.rename(regular_user.id, conv.id, "Hacked")
        assert exc.value.status_code == 404


class TestDelete:
    async def test_delete_cascades_messages(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "To Delete", "gpt-4")
        msg = await svc.append_message(regular_user.id, conv.id, "user", "hello")

        await svc.delete(regular_user.id, conv.id)

        result = await svc.db.execute(select(Conversation).where(Conversation.id == conv.id))
        assert result.scalar_one_or_none() is None

        result = await svc.db.execute(select(Message).where(Message.id == msg.id))
        assert result.scalar_one_or_none() is None

    async def test_delete_other_users_returns_404(self, svc, regular_user, other_user):
        conv = await svc.create(other_user.id, "Not Mine", "gpt-4")
        with pytest.raises(HTTPException) as exc:
            await svc.delete(regular_user.id, conv.id)
        assert exc.value.status_code == 404


class TestAppendMessage:
    async def test_append_message(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "Conv", "gpt-4")
        msg = await svc.append_message(
            regular_user.id,
            conv.id,
            role="assistant",
            content="Hello",
            tool_calls={"call_1": {"name": "foo"}},
            attachments={"file": "a.txt"},
            tokens_in=10,
            tokens_out=5,
        )
        assert msg.conversation_id == conv.id
        assert msg.role == "assistant"
        assert msg.content == "Hello"
        assert msg.tool_calls == {"call_1": {"name": "foo"}}
        assert msg.attachments == {"file": "a.txt"}
        assert msg.tokens_in == 10
        assert msg.tokens_out == 5

    async def test_append_message_other_users_returns_404(self, svc, regular_user, other_user):
        conv = await svc.create(other_user.id, "Not Mine", "gpt-4")
        with pytest.raises(HTTPException) as exc:
            await svc.append_message(regular_user.id, conv.id, "user", "hello")
        assert exc.value.status_code == 404


class TestListMessages:
    async def test_list_messages_oldest_first(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "Conv", "gpt-4")
        m1 = await svc.append_message(regular_user.id, conv.id, "user", "first")
        m2 = await svc.append_message(regular_user.id, conv.id, "user", "second")
        m3 = await svc.append_message(regular_user.id, conv.id, "user", "third")

        msgs = await svc.list_messages(regular_user.id, conv.id)
        assert [m.id for m in msgs] == [m1.id, m2.id, m3.id]

    async def test_list_messages_with_limit(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "Conv", "gpt-4")
        await svc.append_message(regular_user.id, conv.id, "user", "first")
        m2 = await svc.append_message(regular_user.id, conv.id, "user", "second")
        await svc.append_message(regular_user.id, conv.id, "user", "third")

        msgs = await svc.list_messages(regular_user.id, conv.id, limit=2)
        assert len(msgs) == 2
        assert msgs[-1].id == m2.id

    async def test_list_messages_with_before(self, svc, regular_user):
        conv = await svc.create(regular_user.id, "Conv", "gpt-4")
        m1 = await svc.append_message(regular_user.id, conv.id, "user", "first")
        m2 = await svc.append_message(regular_user.id, conv.id, "user", "second")
        m3 = await svc.append_message(regular_user.id, conv.id, "user", "third")

        msgs = await svc.list_messages(regular_user.id, conv.id, before=m3.id)
        assert [m.id for m in msgs] == [m1.id, m2.id]

    async def test_list_messages_other_users_returns_404(self, svc, regular_user, other_user):
        conv = await svc.create(other_user.id, "Not Mine", "gpt-4")
        with pytest.raises(HTTPException) as exc:
            await svc.list_messages(regular_user.id, conv.id)
        assert exc.value.status_code == 404


class TestCreateModelFallback:
    """Test the model_id fallback chain in create()."""

    async def test_create_with_explicit_model_id(self, svc, regular_user):
        """When model_id is provided, use it directly."""
        conv = await svc.create(regular_user.id, "Test", "custom-model")
        assert conv.model_id == "custom-model"

    async def test_create_with_user_default_chat_model(self, svc, regular_user, db_session):
        """When no model_id provided, use user's default_chat_model from preferences."""
        from app.database import UserSettings
        
        # Set user's default chat model
        settings = UserSettings(
            user_id=regular_user.id,
            preferences={"default_chat_model": "user-default-model"}
        )
        db_session.add(settings)
        await db_session.commit()
        
        conv = await svc.create(regular_user.id, "Test")
        assert conv.model_id == "user-default-model"

    async def test_create_fallback_to_first_chat_model(self, svc, regular_user, db_session):
        """When no user default, use first chat-enabled model."""
        from app.database import ModelConfig, Provider
        from uuid import uuid4
        
        # Create a provider
        provider = Provider(
            id=uuid4(),
            name="test-provider",
            provider_type="ollama",
            config={}
        )
        db_session.add(provider)
        await db_session.commit()
        
        # Create chat-enabled models
        model1 = ModelConfig(
            provider_id=provider.id,
            model_id="chat-model-1",
            provider_model_id="chat-model-1",
            display_name="Chat Model 1",
            modality="text",
            endpoint_type="chat",
            is_active=True,
            is_chat_enabled=True
        )
        model2 = ModelConfig(
            provider_id=provider.id,
            model_id="chat-model-2",
            provider_model_id="chat-model-2",
            display_name="Chat Model 2",
            modality="text",
            endpoint_type="chat",
            is_active=True,
            is_chat_enabled=True
        )
        db_session.add_all([model1, model2])
        await db_session.commit()
        
        conv = await svc.create(regular_user.id, "Test")
        # Should use one of the chat-enabled models (order may vary)
        assert conv.model_id in ["chat-model-1", "chat-model-2"]

    async def test_create_fallback_to_default_string(self, svc, regular_user, db_session):
        """When no chat-enabled models exist, fallback to 'default'."""
        # Ensure no chat-enabled models exist (clean state)
        from app.database import ModelConfig
        from sqlalchemy import delete
        await db_session.execute(delete(ModelConfig))
        await db_session.commit()
        
        conv = await svc.create(regular_user.id, "Test")
        assert conv.model_id == "default"

    async def test_create_ignores_non_chat_models(self, svc, regular_user, db_session):
        """Should skip models where is_chat_enabled=False."""
        from app.database import ModelConfig, Provider
        from uuid import uuid4
        
        # Create a provider
        provider = Provider(
            id=uuid4(),
            name="test-provider",
            provider_type="ollama",
            config={}
        )
        db_session.add(provider)
        await db_session.commit()
        
        # Create a non-chat model
        non_chat_model = ModelConfig(
            provider_id=provider.id,
            model_id="non-chat-model",
            provider_model_id="non-chat-model",
            display_name="Non-Chat Model",
            modality="text",
            endpoint_type="completion",
            is_active=True,
            is_chat_enabled=False
        )
        # Create a chat model
        chat_model = ModelConfig(
            provider_id=provider.id,
            model_id="chat-model",
            provider_model_id="chat-model",
            display_name="Chat Model",
            modality="text",
            endpoint_type="chat",
            is_active=True,
            is_chat_enabled=True
        )
        db_session.add_all([non_chat_model, chat_model])
        await db_session.commit()
        
        conv = await svc.create(regular_user.id, "Test")
        assert conv.model_id == "chat-model"
