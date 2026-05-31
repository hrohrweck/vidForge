from datetime import datetime
from uuid import uuid4

from app.api.schemas.chat import MessageOut
from app.database import Message


def test_message_out_with_attachments():
    attachments = [
        {"kind": "image", "url": "/storage/img.png", "mime_type": "image/png"}
    ]
    msg = Message(
        id=uuid4(),
        conversation_id=uuid4(),
        role="user",
        content="hello",
        attachments=attachments,
        created_at=datetime.utcnow(),
    )
    out = MessageOut.model_validate(msg)
    assert out.attachments == attachments


def test_message_out_without_attachments():
    msg = Message(
        id=uuid4(),
        conversation_id=uuid4(),
        role="user",
        content="hello",
        attachments=None,
        created_at=datetime.utcnow(),
    )
    out = MessageOut.model_validate(msg)
    assert out.attachments is None
