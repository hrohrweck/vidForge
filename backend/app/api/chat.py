import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import String, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_from_bearer_or_cookie
from app.api.schemas.chat import (
    ChatStreamMessageCreate,
    ConversationCreate,
    ConversationOut,
    ConversationRename,
    MessageOut,
)
from app.chatbot.service import ChatOrchestrator, ConversationService, TokenUsageService
from app.chatbot.streaming import encode_sse_event
from app.chatbot.tools import ToolContext
from app.database import Conversation, Message, User, get_db
from app.storage import get_storage_backend

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_AUDIO_SIZE = 25 * 1024 * 1024
MAX_SCRIPT_SIZE = 1 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/wav",
    "audio/mp3",
    "audio/x-wav",
    "audio/m4a",
    "audio/ogg",
    "audio/flac",
}
ALLOWED_SCRIPT_TYPES = {"text/plain", "text/markdown", "application/octet-stream"}
ALLOWED_SCRIPT_EXTS = {".txt", ".md", ".json", ".yaml", ".yml", ".csv"}

IMAGE_MAGIC_BYTES = {
    "image/jpeg": [(b"\xff\xd8\xff",)],
    "image/png": [(b"\x89PNG\r\n\x1a\n",)],
    "image/webp": [(b"RIFF", b"WEBP")],
    "image/gif": [(b"GIF87a",), (b"GIF89a",)],
}


class ChatUploadResponse(BaseModel):
    attachment_id: str
    kind: str
    mime_type: str
    size: int
    url: str


def _verify_image_magic_bytes(content: bytes, declared_mime: str) -> bool:
    signatures = IMAGE_MAGIC_BYTES.get(declared_mime)
    if not signatures:
        return False
    for sig in signatures:
        if len(sig) == 1:
            if content.startswith(sig[0]):
                return True
        elif len(sig) == 2:
            if content.startswith(sig[0]) and sig[1] in content[:12]:
                return True
    return False


def _resolve_kind_and_validate(file: UploadFile, content: bytes) -> tuple[str, int]:
    content_type = file.content_type or "application/octet-stream"
    filename = (file.filename or "").lower()
    ext = os.path.splitext(filename)[1]

    if content_type in ALLOWED_IMAGE_TYPES:
        if not _verify_image_magic_bytes(content, content_type):
            raise HTTPException(
                status_code=400,
                detail="Image file magic bytes do not match declared MIME type",
            )
        return "image", MAX_IMAGE_SIZE

    if content_type in ALLOWED_AUDIO_TYPES:
        return "audio", MAX_AUDIO_SIZE

    if content_type in ALLOWED_SCRIPT_TYPES or ext in ALLOWED_SCRIPT_EXTS:
        return "script", MAX_SCRIPT_SIZE

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {content_type}. "
        "Allowed: images (JPEG, PNG, WEBP, GIF), audio (MP3, WAV, M4A, OGG, FLAC), "
        "scripts (TXT, MD, JSON, YAML, CSV)",
    )


@router.post("/uploads", response_model=ChatUploadResponse)
async def upload_chat_attachment(
    current_user: Annotated[User, Depends(get_current_user_from_bearer_or_cookie)],
    file: Annotated[UploadFile, File(...)],
) -> ChatUploadResponse:
    content = await file.read()
    kind, max_size = _resolve_kind_and_validate(file, content)

    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large for {kind}. Max size: {max_size // (1024 * 1024)}MB",
        )

    attachment_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "file")[1]
    storage_path = f"chat-uploads/{current_user.id}/{attachment_id}{ext}"

    storage = get_storage_backend()
    await storage.upload(storage_path, content)
    url = await storage.get_url(storage_path)

    return ChatUploadResponse(
        attachment_id=attachment_id,
        kind=kind,
        mime_type=file.content_type or "application/octet-stream",
        size=len(content),
        url=url,
    )


class ConversationListResponse(BaseModel):
    items: list[ConversationOut]


class MessageListResponse(BaseModel):
    items: list[MessageOut]


class TokenUsageAggregationItem(BaseModel):
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    message_count: int


class TokenUsageAggregationResponse(BaseModel):
    items: list[TokenUsageAggregationItem]


def _ensure_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _date_filter_in_range(
    min_date: datetime | None,
    max_date: datetime | None,
    from_date: datetime | None,
    to_date: datetime | None,
) -> bool:
    if min_date is None or max_date is None:
        return False
    min_cmp = _ensure_naive(min_date)
    max_cmp = _ensure_naive(max_date)
    if from_date:
        from_cmp = _ensure_naive(from_date)
        if max_cmp < from_cmp:
            return False
    if to_date:
        to_cmp = _ensure_naive(to_date)
        if min_cmp > to_cmp:
            return False
    return True


@router.get("/token-usage", response_model=TokenUsageAggregationResponse)
async def get_token_usage(
    from_date: datetime | None = Query(None, description="Start date (ISO format)"),
    to_date: datetime | None = Query(None, description="End date (ISO format)"),
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> TokenUsageAggregationResponse:
    service = TokenUsageService()
    if from_date or to_date:
        range_str = "all"
    else:
        range_str = "30d"
    raw = await service.aggregate(
        db,
        user_id=current_user.id,
        range=range_str,
        group_by="model",
        from_date=from_date,
        to_date=to_date,
    )

    items = []
    for row in raw:
        prompt = row.get("total_tokens_in", 0)
        completion = row.get("total_tokens_out", 0)
        if from_date or to_date:
            if not _date_filter_in_range(
                row.get("min_recorded_at"),
                row.get("max_recorded_at"),
                from_date,
                to_date,
            ):
                continue
        items.append(
            TokenUsageAggregationItem(
                model_id=row.get("model_id", ""),
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=prompt + completion,
                estimated_cost=None,
                message_count=row.get("request_count", 0),
            )
        )
    items.sort(key=lambda x: (-x.total_tokens, x.model_id))

    return TokenUsageAggregationResponse(items=items)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    service = ConversationService(db)
    conversations = await service.list_for_user(current_user.id)
    return ConversationListResponse(
        items=[ConversationOut.model_validate(c) for c in conversations]
    )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    service = ConversationService(db)
    title = data.title or "New Conversation"
    conversation = await service.create(
        user_id=current_user.id,
        title=title,
        model_id=data.model_id,
    )
    return ConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    service = ConversationService(db)
    conversation = await service.get(current_user.id, conversation_id)
    return ConversationOut.model_validate(conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: UUID,
    data: ConversationRename,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    service = ConversationService(db)
    conversation = await service.rename(current_user.id, conversation_id, data.title)
    return ConversationOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ConversationService(db)
    await service.delete(current_user.id, conversation_id)


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    before: UUID | None = None,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    service = ConversationService(db)
    messages = await service.list_messages(
        user_id=current_user.id,
        conv_id=conversation_id,
        limit=limit,
        before=before,
    )
    return MessageListResponse(items=[MessageOut.model_validate(m) for m in messages])


@router.post("/conversations/{conversation_id}/messages")
async def create_message_stream(
    conversation_id: UUID,
    data: ChatStreamMessageCreate,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = ConversationService(db)
    conversation = await service.get(current_user.id, conversation_id)
    model_id = data.model_id or conversation.model_id

    async def event_generator():
        orchestrator = ChatOrchestrator(db)
        ctx = ToolContext(
            user_id=str(current_user.id),
            db=db,
            request_id="",
            conversation_id=str(conversation_id),
        )
        try:
            async for event_type, event_data in orchestrator.run_turn(
                conversation_id=conversation_id,
                user_message=data.content,
                attachments=data.attachments,
                model_id=model_id,
                ctx=ctx,
            ):
                yield encode_sse_event(event_type, event_data)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("Chat stream error")
            yield encode_sse_event("error", {"reason": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/search")
async def search_chat(
    q: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
):
    result = await db.execute(
        select(Message, Conversation)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == current_user.id,
            Conversation.archived_at.is_(None),
            or_(
                Message.content.ilike(f"%{q}%"),
                Message.tool_calls.cast(String).ilike(f"%{q}%"),
            ),
        )
        .order_by(Message.created_at.desc())
        .limit(50)
    )
    rows = result.all()
    return [
        {
            "message_id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "conversation_title": c.title,
            "content": m.content[:200],
            "role": m.role,
            "created_at": m.created_at.isoformat(),
        }
        for m, c in rows
    ]
