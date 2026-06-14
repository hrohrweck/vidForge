import pytest


@pytest.mark.asyncio
async def test_conversation_metadata_roundtrip(db_session, conversation):
    conversation.metadata_ = {"chat_autonomy": "autonomous"}
    await db_session.commit()
    await db_session.refresh(conversation)
    assert conversation.metadata_["chat_autonomy"] == "autonomous"


@pytest.mark.asyncio
async def test_conversation_metadata_default_is_none(db_session, conversation):
    await db_session.refresh(conversation)
    assert conversation.metadata_ is None
