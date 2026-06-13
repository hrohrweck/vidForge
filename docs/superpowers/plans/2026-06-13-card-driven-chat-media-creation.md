# Card-Driven Chat Media Creation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users create videos from chat through an interactive card workflow: approve an editable draft, review the scene plan, review generated images/videos, and export — all inside chat messages, with async updates and a per-conversation autonomy toggle.

**Architecture:** Backend posts stage-transition messages with `job_card` attachments; the frontend renders those attachments as interactive cards that call existing job/scene REST APIs and listen to the existing job WebSocket. A new `JobChatNotifier` service hooks into the worker dispatcher, and a `ChatAutonomyService` decides whether to ask for confirmation or run autonomously.

**Tech Stack:** FastAPI, SQLAlchemy + Alembic, Celery, Redis, React + TypeScript + Zustand, WebSocket.

---

## File map

| File | Responsibility |
|---|---|
| `backend/app/database.py` | Add `metadata` JSONB column to `Conversation`. |
| `backend/alembic/versions/...` | Migration for the new column. |
| `backend/app/services/chat_autonomy_service.py` | Read default from `UserSettings`, read/write per-conversation override. |
| `backend/app/api/chat.py` | New `GET/POST /conversations/{id}/autonomy` endpoints. |
| `backend/app/api/schemas/chat.py` | New Pydantic schemas for autonomy requests/responses. |
| `backend/app/services/job_chat_notifier.py` | Post card messages at pipeline stage transitions. |
| `backend/app/workers/dispatcher.py` | Call `JobChatNotifier` after planning, images, videos, rendering, failure. |
| `backend/app/workers/tasks.py` | Use `JobChatNotifier` for final completion; avoid duplicate messages. |
| `backend/app/chatbot/tools.py` | Add `present_job_draft`, `set_chat_autonomy`, `get_chat_autonomy` tools. |
| `backend/app/chatbot/service.py` | Inject autonomy mode into system prompt; pause for draft in confirm mode. |
| `frontend/src/stores/chat.ts` | Extend `Message`/`Attachment` types to support `job_card`. |
| `frontend/src/api/chat.ts` | Add autonomy endpoints; expose job/scene endpoints if not present. |
| `frontend/src/components/chat/MessageBubble.tsx` | Route `job_card` attachments to card components. |
| `frontend/src/components/chat/cards/*.tsx` | Card components for draft, scene plan, image/video review, completed, error. |

---

## Task 1: Add `Conversation.metadata` column

**Files:**
- Modify: `backend/app/database.py:111-133`
- Create: `backend/alembic/versions/20260613_add_conversation_metadata.py`
- Test: `backend/tests/integration/test_model_config_migration.py` (pattern) or a one-off check

- [ ] **Step 1: Add the column to the model**

Add inside `class Conversation`:

```python
metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 2: Generate the migration**

Run:

```bash
cd backend
alembic revision --autogenerate -m "add conversation metadata"
```

If autogenerate does not pick it up, create the migration manually:

```python
"""add conversation metadata

Revision ID: 20260613_add_conversation_metadata
Revises: <previous-head>
Create Date: 2026-06-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '20260613_add_conversation_metadata'
down_revision = '<previous-head>'


def upgrade() -> None:
    op.add_column('conversation', sa.Column('metadata', pg.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('conversation', 'metadata')
```

- [ ] **Step 3: Run the migration locally**

```bash
cd backend
alembic upgrade head
```

Expected: migration applies successfully.

- [ ] **Step 4: Commit**

```bash
git add backend/app/database.py backend/alembic/versions/20260613_add_conversation_metadata.py
git commit -m "feat(chat): add Conversation.metadata column for autonomy override"
```

---

## Task 2: Implement `ChatAutonomyService` and API endpoints

**Files:**
- Create: `backend/app/services/chat_autonomy_service.py`
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/schemas/chat.py`
- Test: `backend/tests/unit/test_chat_autonomy_service.py`

- [ ] **Step 1: Write the service**

Create `backend/app/services/chat_autonomy_service.py`:

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Conversation, User, UserSettings

AutonomyMode = Literal["confirm", "autonomous"]
DEFAULT_MODE: AutonomyMode = "confirm"


class ChatAutonomyService:
    """Manage the assistant's confirmation behavior per conversation."""

    @staticmethod
    async def get_default_mode(db: AsyncSession, user_id: UUID) -> AutonomyMode:
        result = await db.execute(
            select(UserSettings.preferences).where(UserSettings.user_id == user_id)
        )
        prefs = result.scalar_one_or_none() or {}
        mode = prefs.get("chat_autonomy")
        if mode in ("confirm", "autonomous"):
            return mode  # type: ignore[return-value]
        return DEFAULT_MODE

    @staticmethod
    async def get_mode(db: AsyncSession, conversation_id: UUID, user_id: UUID) -> AutonomyMode:
        result = await db.execute(
            select(Conversation.metadata).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        metadata = result.scalar_one_or_none() or {}
        mode = metadata.get("chat_autonomy")
        if mode in ("confirm", "autonomous"):
            return mode  # type: ignore[return-value]
        return await ChatAutonomyService.get_default_mode(db, user_id)

    @staticmethod
    async def set_mode(
        db: AsyncSession,
        conversation_id: UUID,
        user_id: UUID,
        mode: AutonomyMode,
    ) -> AutonomyMode:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError("Conversation not found")
        conversation.metadata = {**(conversation.metadata or {}), "chat_autonomy": mode}
        await db.commit()
        await db.refresh(conversation)
        return mode
```

- [ ] **Step 2: Add schemas**

In `backend/app/api/schemas/chat.py`, append:

```python
class AutonomyModeRequest(BaseModel):
    mode: Literal["confirm", "autonomous"]


class AutonomyModeResponse(BaseModel):
    mode: Literal["confirm", "autonomous"]
```

- [ ] **Step 3: Add endpoints**

In `backend/app/api/chat.py`, after the conversation deletion endpoint, add:

```python
from app.services.chat_autonomy_service import ChatAutonomyService
from app.api.schemas.chat import AutonomyModeRequest, AutonomyModeResponse


@router.get("/conversations/{conversation_id}/autonomy", response_model=AutonomyModeResponse)
async def get_chat_autonomy(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> AutonomyModeResponse:
    mode = await ChatAutonomyService.get_mode(db, conversation_id, current_user.id)
    return AutonomyModeResponse(mode=mode)


@router.post("/conversations/{conversation_id}/autonomy", response_model=AutonomyModeResponse)
async def set_chat_autonomy(
    conversation_id: UUID,
    request: AutonomyModeRequest,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> AutonomyModeResponse:
    mode = await ChatAutonomyService.set_mode(
        db, conversation_id, current_user.id, request.mode
    )
    return AutonomyModeResponse(mode=mode)
```

- [ ] **Step 4: Write unit tests**

Create `backend/tests/unit/test_chat_autonomy_service.py`:

```python
import pytest
from uuid import uuid4

from app.services.chat_autonomy_service import ChatAutonomyService


@pytest.mark.asyncio
async def test_default_mode_is_confirm(db, user):
    mode = await ChatAutonomyService.get_default_mode(db, user.id)
    assert mode == "confirm"


@pytest.mark.asyncio
async def test_conversation_override(db, user, conversation):
    await ChatAutonomyService.set_mode(db, conversation.id, user.id, "autonomous")
    mode = await ChatAutonomyService.get_mode(db, conversation.id, user.id)
    assert mode == "autonomous"
```

Use existing fixtures or add minimal ones.

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_chat_autonomy_service.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/chat_autonomy_service.py backend/app/api/chat.py backend/app/api/schemas/chat.py backend/tests/unit/test_chat_autonomy_service.py
git commit -m "feat(chat): add ChatAutonomyService and conversation autonomy endpoints"
```

---

## Task 3: Implement `JobChatNotifier`

**Files:**
- Create: `backend/app/services/job_chat_notifier.py`
- Modify: `backend/app/workers/dispatcher.py`
- Modify: `backend/app/workers/tasks.py`
- Test: `backend/tests/unit/test_job_chat_notifier.py`

- [ ] **Step 1: Write the notifier service**

Create `backend/app/services/job_chat_notifier.py`:

```python
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.streaming import ws_manager
from app.database import Conversation, Job, Message, VideoScene
from app.services.chat_autonomy_service import ChatAutonomyService

logger = logging.getLogger(__name__)


class JobChatNotifier:
    """Post interactive job-card messages into the linked chat conversation."""

    @staticmethod
    async def _should_skip_intermediate(db: AsyncSession, conversation_id: UUID) -> bool:
        try:
            result = await db.execute(
                select(Conversation.user_id).where(Conversation.id == conversation_id)
            )
            user_id = result.scalar_one_or_none()
            if user_id is None:
                return True
            mode = await ChatAutonomyService.get_mode(db, conversation_id, user_id)
            return mode == "autonomous"
        except Exception:
            logger.exception("Failed to read autonomy mode; defaulting to confirm")
            return False

    @staticmethod
    async def _post_card(
        db: AsyncSession,
        job: Job,
        card_type: str,
        title: str,
        data: dict[str, Any],
        actions: list[str],
        content: str,
    ) -> None:
        if not job.chat_conversation_id:
            return

        message = Message(
            id=uuid4(),
            conversation_id=job.chat_conversation_id,
            role="assistant",
            content=content,
            job_id=job.id,
            attachments=[
                {
                    "kind": "job_card",
                    "card_type": card_type,
                    "job_id": str(job.id),
                    "title": title,
                    "data": data,
                    "actions": actions,
                }
            ],
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        await ws_manager.broadcast_chat_message(
            str(job.chat_conversation_id), str(message.id)
        )

    @staticmethod
    async def notify_planned(db: AsyncSession, job: Job) -> None:
        if await JobChatNotifier._should_skip_intermediate(db, job.chat_conversation_id):
            return

        result = await db.execute(
            select(VideoScene).where(VideoScene.job_id == job.id).order_by(VideoScene.scene_number)
        )
        scenes = result.scalars().all()
        data = {
            "scenes": [
                {
                    "scene_number": s.scene_number,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "visual_description": s.visual_description,
                    "image_prompt": s.image_prompt,
                    "mood": s.mood,
                    "camera_movement": s.camera_movement,
                }
                for s in scenes
            ]
        }
        await JobChatNotifier._post_card(
            db,
            job,
            card_type="scene_plan",
            title="Scene plan ready",
            data=data,
            actions=["generate_images"],
            content=f"Planned {len(data['scenes'])} scenes for **{job.title}**. Review them and click Generate images to continue.",
        )

    @staticmethod
    async def notify_images_ready(db: AsyncSession, job: Job) -> None:
        if await JobChatNotifier._should_skip_intermediate(db, job.chat_conversation_id):
            return

        result = await db.execute(
            select(VideoScene).where(VideoScene.job_id == job.id).order_by(VideoScene.scene_number)
        )
        scenes = result.scalars().all()
        data = {
            "scenes": [
                {
                    "scene_number": s.scene_number,
                    "thumbnail_url": s.thumbnail_path,
                    "status": s.status,
                }
                for s in scenes
            ]
        }
        await JobChatNotifier._post_card(
            db,
            job,
            card_type="image_review",
            title="Images ready",
            data=data,
            actions=["generate_videos"],
            content=f"Reference images are ready for **{job.title}**. Click Generate videos to continue.",
        )

    @staticmethod
    async def notify_videos_ready(db: AsyncSession, job: Job) -> None:
        if await JobChatNotifier._should_skip_intermediate(db, job.chat_conversation_id):
            return

        result = await db.execute(
            select(VideoScene).where(VideoScene.job_id == job.id).order_by(VideoScene.scene_number)
        )
        scenes = result.scalars().all()
        data = {
            "scenes": [
                {
                    "scene_number": s.scene_number,
                    "preview_url": s.generated_video_path,
                    "status": s.status,
                }
                for s in scenes
            ]
        }
        await JobChatNotifier._post_card(
            db,
            job,
            card_type="video_review",
            title="Videos ready",
            data=data,
            actions=["export"],
            content=f"Video clips are ready for **{job.title}**. Click Export to render the final video.",
        )

    @staticmethod
    async def notify_completed(db: AsyncSession, job: Job) -> None:
        if not job.chat_conversation_id:
            return

        from app.storage import get_storage_backend

        storage = get_storage_backend()
        output_url = await storage.get_url(job.output_path) if job.output_path else None
        preview_url = await storage.get_url(job.preview_path) if job.preview_path else None
        thumbnail_url = await storage.get_url(job.thumbnail_path) if job.thumbnail_path else None

        # Final completion is always posted, even in autonomous mode.
        message = Message(
            id=uuid4(),
            conversation_id=job.chat_conversation_id,
            role="assistant",
            content=f"Your video **{job.title}** is ready.",
            job_id=job.id,
            attachments=[
                {
                    "kind": "job_card",
                    "card_type": "job_completed",
                    "job_id": str(job.id),
                    "title": "Video completed",
                    "data": {
                        "output_url": output_url,
                        "preview_url": preview_url,
                        "thumbnail_url": thumbnail_url,
                    },
                    "actions": ["download"],
                }
            ],
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        await ws_manager.broadcast_chat_message(
            str(job.chat_conversation_id), str(message.id)
        )

    @staticmethod
    async def notify_failed(db: AsyncSession, job: Job, error_message: str) -> None:
        if not job.chat_conversation_id:
            return

        await JobChatNotifier._post_card(
            db,
            job,
            card_type="job_error",
            title="Job failed",
            data={"error_message": error_message},
            actions=["retry", "cancel"],
            content=f"The job **{job.title}** failed: {error_message}",
        )
```

- [ ] **Step 2: Wire into dispatcher**

In `backend/app/workers/dispatcher.py`, import and call the notifier after each successful/failed stage.

After planning completes (`job.stage = "planned"` around line 143):

```python
from app.services.job_chat_notifier import JobChatNotifier

await JobChatNotifier.notify_planned(db, job)
```

After images complete (`job.stage = "images_ready"` around line 162):

```python
await JobChatNotifier.notify_images_ready(db, job)
```

After videos complete (`job.stage = "videos_ready"` around line 187):

```python
await JobChatNotifier.notify_videos_ready(db, job)
```

After rendering completes (around line 238), call:

```python
await JobChatNotifier.notify_completed(db, job)
```

In the exception handler around line 265, call:

```python
await JobChatNotifier.notify_failed(db, job, str(exc))
```

- [ ] **Step 3: Update final completion path in tasks.py**

In `backend/app/workers/tasks.py`, replace the existing `_post_completion_message` body so it delegates to `JobChatNotifier` and removes the duplicate-message guard (the notifier does not need it for the final card, but keep the guard if other callers rely on it). For now, simplify to:

```python
async def _post_completion_message(job_id: UUID, db: AsyncSession | None = None) -> None:
    if db is None:
        async with ctx.session_factory() as db:
            return await _post_completion_message(job_id, db=db)

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job or not job.chat_conversation_id:
        return

    dup_result = await db.execute(
        select(Message).where(
            Message.conversation_id == job.chat_conversation_id,
            Message.job_id == job.id,
            Message.attachments.isnot(None),
        )
    )
    if dup_result.scalar_one_or_none():
        return

    await JobChatNotifier.notify_completed(db, job)
```

- [ ] **Step 4: Write unit tests**

Create `backend/tests/unit/test_job_chat_notifier.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.job_chat_notifier import JobChatNotifier
from app.database import Job, VideoScene


@pytest.mark.asyncio
async def test_notify_planned_posts_scene_plan_card(db, user, conversation):
    job = Job(
        id=uuid4(),
        title="Test",
        user_id=user.id,
        chat_conversation_id=conversation.id,
        status="processing",
        stage="planned",
    )
    db.add(job)
    await db.commit()

    scene = VideoScene(
        id=uuid4(),
        job_id=job.id,
        scene_number=1,
        start_time=0,
        end_time=5,
        visual_description="desc",
        image_prompt="prompt",
        mood="neutral",
        camera_movement="static",
    )
    db.add(scene)
    await db.commit()

    with patch("app.services.job_chat_notifier.ws_manager.broadcast_chat_message", new_callable=AsyncMock) as mock_broadcast:
        await JobChatNotifier.notify_planned(db, job)
        mock_broadcast.assert_awaited_once()

    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    msg = result.scalar_one()
    assert msg.attachments[0]["card_type"] == "scene_plan"
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_job_chat_notifier.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/job_chat_notifier.py backend/app/workers/dispatcher.py backend/app/workers/tasks.py backend/tests/unit/test_job_chat_notifier.py
git commit -m "feat(chat): add JobChatNotifier for pipeline stage cards"
```

---

## Task 4: Add chat tools and autonomy-aware orchestration

**Files:**
- Modify: `backend/app/chatbot/tools.py`
- Modify: `backend/app/chatbot/service.py`
- Test: `backend/tests/unit/test_chat_tools_autonomy.py`

- [ ] **Step 1: Add the new tools in `tools.py`**

Add handlers near the other job tools:

```python
async def _handle_present_job_draft(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Return a job draft payload for the frontend to render as a card."""
    template = args.get("template")
    prompt = args.get("prompt")
    if not template or not prompt:
        return {"error": "missing_argument", "message": "'template' and 'prompt' are required"}

    draft: dict[str, Any] = {
        "template": template,
        "prompt": prompt,
        "duration": args.get("duration", 30),
        "style": args.get("style", "realistic"),
        "aspect_ratio": args.get("aspect_ratio", "16:9"),
    }
    if "avatars" in args:
        raw = args["avatars"]
        draft["avatars"] = [
            {"avatar_id": str(item)} if isinstance(item, str) else item
            for item in raw
        ]
    if "image_model" in args:
        draft["image_model"] = args["image_model"]
    if "video_model" in args:
        draft["video_model"] = args["video_model"]

    return {"kind": "job_draft", "draft": draft}


async def _handle_set_chat_autonomy(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Set the confirmation mode for this conversation."""
    mode = args.get("mode")
    if mode not in ("confirm", "autonomous"):
        return {"error": "invalid_mode", "message": "mode must be 'confirm' or 'autonomous'"}

    if not ctx.conversation_id or not ctx.db:
        return {"error": "missing_context", "message": "Conversation context required"}

    from app.services.chat_autonomy_service import ChatAutonomyService

    await ChatAutonomyService.set_mode(
        ctx.db, UUID(ctx.conversation_id), ctx.user_id, mode
    )
    return {"mode": mode}


async def _handle_get_chat_autonomy(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Return the current confirmation mode for this conversation."""
    if not ctx.conversation_id or not ctx.db:
        return {"mode": "confirm"}

    from app.services.chat_autonomy_service import ChatAutonomyService

    mode = await ChatAutonomyService.get_mode(
        ctx.db, UUID(ctx.conversation_id), ctx.user_id
    )
    return {"mode": mode}
```

Register them in `create_builtin_registry`:

```python
    registry.register(
        ToolDefinition(
            name="present_job_draft",
            description="Present a job draft to the user for approval before creating it.",
            input_schema={
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "Template ID or name"},
                    "prompt": {"type": "string", "description": "Video prompt"},
                    "duration": {"type": "number", "description": "Target duration in seconds"},
                    "style": {"type": "string", "description": "Visual style"},
                    "aspect_ratio": {"type": "string", "description": "Aspect ratio"},
                    "avatars": {"type": "array", "items": {"type": "string"}, "description": "Avatar IDs"},
                    "image_model": {"type": "string"},
                    "video_model": {"type": "string"},
                },
                "required": ["template", "prompt"],
            },
            handler=_handle_present_job_draft,
        )
    )

    registry.register(
        ToolDefinition(
            name="set_chat_autonomy",
            description="Set the assistant's confirmation mode for this conversation.",
            input_schema={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["confirm", "autonomous"]},
                },
                "required": ["mode"],
            },
            handler=_handle_set_chat_autonomy,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_chat_autonomy",
            description="Get the current confirmation mode for this conversation.",
            input_schema={"type": "object", "properties": {}},
            handler=_handle_get_chat_autonomy,
        )
    )
```

- [ ] **Step 2: Make the orchestrator autonomy-aware**

In `backend/app/chatbot/service.py`:

1. Change `SYSTEM_PROMPT` from a constant to a method by replacing the class-level string with a helper function, or build the system message dynamically in `run_turn`.

Simpler: keep the constant but add a placeholder and format it when building history. Update the constant to include:

```python
SYSTEM_PROMPT_TEMPLATE = (
    "You are VidForge's assistant. ...\n\n"
    "Current confirmation mode: {autonomy_mode}. "
    "In 'confirm' mode, always call present_job_draft and wait for user approval before creating a job. "
    "In 'autonomous' mode, create the job directly and do not show intermediate review cards.\n\n"
    ...
)
```

Then in `run_turn`, after resolving the model and before the loop, read the autonomy mode and build the system prompt:

```python
        autonomy_mode = "confirm"
        if ctx.conversation_id:
            autonomy_mode = await ChatAutonomyService.get_mode(
                self.db, UUID(ctx.conversation_id), user_id
            )
        system_content = SYSTEM_PROMPT_TEMPLATE.format(autonomy_mode=autonomy_mode)
```

Replace `self._trim_messages(history)` to use `system_content` instead of the constant.

Update `_trim_messages` signature to accept the system content:

```python
    def _trim_messages(self, messages: list[dict[str, Any]], system_content: str) -> list[dict[str, Any]]:
        trimmed = list(messages)
        while trimmed and self._projected_tokens(trimmed) > self.context_limit:
            trimmed.pop(0)
        return [{"role": "system", "content": system_content}, *trimmed]
```

Call it with the dynamic system content in `run_turn`.

- [ ] **Step 3: Update `_should_pause_after_tool`**

Add `present_job_draft` to the pause list so the assistant stops and the user sees the draft card:

```python
    def _should_pause_after_tool(self, name: str, result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        if name == "present_job_draft" and result.get("kind") == "job_draft":
            return True
        if name == "create_job" and result.get("job_id"):
            return True
        ...
```

- [ ] **Step 4: Tests**

Create `backend/tests/unit/test_chat_tools_autonomy.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.chatbot.tools import ToolContext, _handle_present_job_draft, _handle_set_chat_autonomy


@pytest.mark.asyncio
async def test_present_job_draft_returns_card_payload():
    ctx = ToolContext(user_id="user-1")
    result = await _handle_present_job_draft(
        ctx,
        {"template": "prompt-to-video", "prompt": "Niki dancing", "duration": 25, "avatars": [str(uuid4())]},
    )
    assert result["kind"] == "job_draft"
    assert result["draft"]["duration"] == 25


@pytest.mark.asyncio
async def test_set_chat_autonomy_updates_mode():
    from unittest.mock import MagicMock
    db = AsyncMock()
    ctx = ToolContext(user_id="user-1", db=db, conversation_id=str(uuid4()))
    with patch("app.chatbot.tools.ChatAutonomyService.set_mode", new_callable=AsyncMock) as mock:
        result = await _handle_set_chat_autonomy(ctx, {"mode": "autonomous"})
        assert result["mode"] == "autonomous"
        mock.assert_awaited_once()
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_chat_tools_autonomy.py tests/unit/test_chat_tools_jobs.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/chatbot/tools.py backend/app/chatbot/service.py backend/tests/unit/test_chat_tools_autonomy.py
git commit -m "feat(chat): add autonomy tools and orchestrator awareness"
```

---

## Task 5: Frontend card infrastructure

**Files:**
- Modify: `frontend/src/stores/chat.ts`
- Create: `frontend/src/components/chat/cards/JobDraftCard.tsx`
- Create: `frontend/src/components/chat/cards/ScenePlanCard.tsx`
- Create: `frontend/src/components/chat/cards/ImageReviewCard.tsx`
- Create: `frontend/src/components/chat/cards/VideoReviewCard.tsx`
- Create: `frontend/src/components/chat/cards/JobCompletedCard.tsx`
- Create: `frontend/src/components/chat/cards/JobErrorCard.tsx`
- Create: `frontend/src/components/chat/cards/index.ts`
- Modify: `frontend/src/components/chat/MessageBubble.tsx`
- Modify: `frontend/src/api/chat.ts`

- [ ] **Step 1: Extend chat types**

In `frontend/src/stores/chat.ts`, update the `Attachment` and `Message` interfaces:

```typescript
export interface JobCardAttachment {
  kind: 'job_card'
  card_type: 'job_draft' | 'scene_plan' | 'image_review' | 'video_review' | 'job_completed' | 'job_error'
  job_id: string | null
  title: string
  data: Record<string, unknown>
  actions: string[]
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  createdAt: string
  attachments?: Array<JobCardAttachment | {url: string; type?: string; name?: string; kind?: string; mime_type?: string}>
  toolCallId?: string
  jobId?: string | null
  mediaResult?: { kind: string; url: string; mime_type?: string }
}
```

- [ ] **Step 2: Add API helpers**

In `frontend/src/api/chat.ts`, add:

```typescript
export const chatApi = {
  // ... existing methods

  getAutonomy: async (conversationId: string): Promise<{mode: 'confirm' | 'autonomous'}> => {
    const res = await client.get(`/chat/conversations/${conversationId}/autonomy`)
    return res.data
  },

  setAutonomy: async (conversationId: string, mode: 'confirm' | 'autonomous'): Promise<void> => {
    await client.post(`/chat/conversations/${conversationId}/autonomy`, { mode })
  },
}
```

Also ensure the existing `jobsApi` or `chatApi` exposes:

```typescript
createJob: (payload: unknown) => client.post('/jobs', payload),
getJob: (id: string) => client.get(`/jobs/${id}`),
getJobScenes: (id: string) => client.get(`/jobs/${id}/scenes`),
generateAllImages: (id: string) => client.post(`/jobs/${id}/scenes/generate-all-images`),
generateAllVideos: (id: string) => client.post(`/jobs/${id}/scenes/generate-all-videos`),
exportJob: (id: string, options?: unknown) => client.post(`/jobs/${id}/export`, options),
retryJob: (id: string) => client.post(`/jobs/${id}/retry`),
cancelJob: (id: string) => client.post(`/jobs/${id}/cancel`),
```

- [ ] **Step 3: Create `JobDraftCard`**

Create `frontend/src/components/chat/cards/JobDraftCard.tsx`:

```tsx
import { useState } from 'react'
import { jobsApi } from '../../../api/chat'

interface JobDraftCardProps {
  data: {
    template: string
    prompt: string
    duration: number
    style: string
    aspect_ratio: string
    avatars?: Array<{avatar_id: string; avatar_name?: string}>
    image_model?: string
    video_model?: string
  }
  onCreated?: (jobId: string) => void
}

export function JobDraftCard({ data, onCreated }: JobDraftCardProps) {
  const [draft, setDraft] = useState(data)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      const payload = {
        title: draft.prompt.slice(0, 50),
        template_id: draft.template,
        input_data: {
          prompt: draft.prompt,
          duration: draft.duration,
          style: draft.style,
          aspect_ratio: draft.aspect_ratio,
          avatars: draft.avatars,
          image_model: draft.image_model,
          video_model: draft.video_model,
        },
        auto_start: true,
      }
      const res = await jobsApi.createJob(payload)
      onCreated?.(res.data.id)
    } catch (err: any) {
      setError(err.response?.data?.detail?.errors?.join(', ') || 'Failed to create job')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="rounded border p-3 space-y-2 bg-muted/30">
      <h4 className="font-medium">Job draft</h4>
      <textarea
        className="w-full rounded border p-2 text-sm"
        value={draft.prompt}
        onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
        rows={2}
      />
      <div className="flex gap-2">
        <input
          type="number"
          className="w-24 rounded border p-2 text-sm"
          value={draft.duration}
          onChange={(e) => setDraft({ ...draft, duration: Number(e.target.value) })}
        />
        <select
          className="rounded border p-2 text-sm"
          value={draft.style}
          onChange={(e) => setDraft({ ...draft, style: e.target.value })}
        >
          <option value="realistic">realistic</option>
          <option value="anime">anime</option>
          <option value="manga">manga</option>
        </select>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <button
        onClick={handleCreate}
        disabled={creating}
        className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
      >
        {creating ? 'Creating...' : 'Create'}
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Create `ScenePlanCard`**

Create `frontend/src/components/chat/cards/ScenePlanCard.tsx`:

```tsx
import { useState } from 'react'
import { jobsApi } from '../../../api/chat'

interface Scene {
  scene_number: number
  start_time: number
  end_time: number
  visual_description: string
  image_prompt: string
  mood: string
  camera_movement: string
}

interface ScenePlanCardProps {
  jobId: string
  data: { scenes: Scene[] }
}

export function ScenePlanCard({ jobId, data }: ScenePlanCardProps) {
  const [loading, setLoading] = useState(false)

  const generateImages = async () => {
    setLoading(true)
    try {
      await jobsApi.generateAllImages(jobId)
    } finally {
      // Button stays disabled while job progresses; card will re-render via WS.
    }
  }

  return (
    <div className="rounded border p-3 space-y-2 bg-muted/30">
      <h4 className="font-medium">{data.scenes.length} scenes planned</h4>
      <ul className="max-h-60 overflow-y-auto space-y-2 text-xs">
        {data.scenes.map((s) => (
          <li key={s.scene_number} className="rounded border p-2">
            <strong>Scene {s.scene_number}</strong> ({s.start_time}s - {s.end_time}s)<br />
            {s.visual_description}
          </li>
        ))}
      </ul>
      <button
        onClick={generateImages}
        disabled={loading}
        className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
      >
        {loading ? 'Queueing...' : 'Generate images'}
      </button>
    </div>
  )
}
```

- [ ] **Step 5: Create `ImageReviewCard`, `VideoReviewCard`, `JobCompletedCard`, `JobErrorCard`**

Follow the same pattern:
- `ImageReviewCard` calls `jobsApi.generateAllVideos(jobId)`.
- `VideoReviewCard` calls `jobsApi.exportJob(jobId)`.
- `JobCompletedCard` shows the preview/output URLs.
- `JobErrorCard` offers **Retry** (`jobsApi.retryJob`) and **Cancel** (`jobsApi.cancelJob`).

Create `frontend/src/components/chat/cards/index.ts`:

```typescript
export { JobDraftCard } from './JobDraftCard'
export { ScenePlanCard } from './ScenePlanCard'
export { ImageReviewCard } from './ImageReviewCard'
export { VideoReviewCard } from './VideoReviewCard'
export { JobCompletedCard } from './JobCompletedCard'
export { JobErrorCard } from './JobErrorCard'
```

- [ ] **Step 6: Wire cards into `MessageBubble`**

In `frontend/src/components/chat/MessageBubble.tsx`, inside the assistant branch, before rendering `AssistantContent`, render `job_card` attachments:

```tsx
import { JobDraftCard, ScenePlanCard, ImageReviewCard, VideoReviewCard, JobCompletedCard, JobErrorCard } from './cards'

function JobCardAttachment({ attachment, conversationId }: { attachment: JobCardAttachment; conversationId?: string }) {
  const { card_type, job_id, data } = attachment
  switch (card_type) {
    case 'job_draft':
      return <JobDraftCard data={data as any} />
    case 'scene_plan':
      return job_id ? <ScenePlanCard jobId={job_id} data={data as any} /> : null
    case 'image_review':
      return job_id ? <ImageReviewCard jobId={job_id} data={data as any} /> : null
    case 'video_review':
      return job_id ? <VideoReviewCard jobId={job_id} data={data as any} /> : null
    case 'job_completed':
      return job_id ? <JobCompletedCard jobId={job_id} data={data as any} /> : null
    case 'job_error':
      return job_id ? <JobErrorCard jobId={job_id} data={data as any} /> : null
    default:
      return null
  }
}
```

Render it in `MessageBubble` after attachments but before `AssistantContent`.

- [ ] **Step 7: Type-check and build**

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Expected: no type errors, build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/stores/chat.ts frontend/src/api/chat.ts frontend/src/components/chat/cards frontend/src/components/chat/MessageBubble.tsx
git commit -m "feat(chat): render job_card attachments as interactive pipeline cards"
```

---

## Task 6: User settings default for chat autonomy

**Files:**
- Modify: backend user settings endpoint/schema (find the relevant files)
- Modify: frontend settings page
- Test: manual

- [ ] **Step 1: Add backend preference**

Locate the user settings endpoint (likely `backend/app/api/users.py` or `backend/app/api/settings.py`). Add `chat_autonomy` to the preferences schema/default.

Example if preferences are a free-form dict, no schema change needed; just ensure the frontend can save:

```python
# In settings update handler
prefs = user.settings.preferences or {}
prefs["chat_autonomy"] = request.chat_autonomy
user.settings.preferences = prefs
```

- [ ] **Step 2: Add frontend toggle**

In the settings page, add a select/toggle bound to `chat_autonomy` (`confirm` | `autonomous`).

- [ ] **Step 3: Fetch default on conversation creation**

When a new conversation is created, the backend already reads `UserSettings.default_chat_model`. Extend that path (or the frontend) to also default the conversation metadata to the user's autonomy preference.

Simpler: `ChatAutonomyService.get_mode` already falls back to `UserSettings.preferences["chat_autonomy"]`, so no extra work needed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/users.py frontend/src/pages/Settings.tsx  # adjust paths as needed
git commit -m "feat(settings): add default chat autonomy preference"
```

---

## Task 7: Integration, testing, and deployment

- [ ] **Step 1: Run backend tests**

```bash
cd backend
uv run pytest tests/unit/test_chat_autonomy_service.py tests/unit/test_job_chat_notifier.py tests/unit/test_chat_tools_autonomy.py tests/unit/test_chat_tools_jobs.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run frontend type check and build**

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Expected: no errors.

- [ ] **Step 3: Manual end-to-end test**

1. Start the stack: `cd docker && docker compose up -d --build`
2. Open the chat UI.
3. Ask: *“Create a 15-second video of Niki dancing.”*
4. Verify a `JobDraftCard` appears.
5. Click **Create**.
6. Verify the job plans and a `ScenePlanCard` appears.
7. Click **Generate images**.
8. Verify images generate and an `ImageReviewCard` appears.
9. Continue through videos and export.
10. Say *“just do it”* in a new conversation and verify the workflow runs without intermediate cards.

- [ ] **Step 4: Add a minimal E2E test (optional but recommended)**

Create `frontend/e2e/chat-job-cards.spec.ts`:

```typescript
import { test, expect } from '@playwright/test'

test('chat shows draft card and progresses through scene plan', async ({ page }) => {
  await page.goto('/chat')
  // Fill in auth/login steps as required by existing E2E setup
  await page.fill('[data-testid="chat-input"]', 'Create a 10-second video of Niki dancing')
  await page.click('[data-testid="chat-send"]')
  await expect(page.locator('text=Job draft')).toBeVisible()
  await page.click('text=Create')
  await expect(page.locator('text=scenes planned')).toBeVisible({ timeout: 60000 })
})
```

- [ ] **Step 5: Commit and push**

```bash
git add frontend/e2e/chat-job-cards.spec.ts
git commit -m "test(e2e): add chat job card flow smoke test"
git push
```

- [ ] **Step 6: Deploy**

```bash
cd docker
docker compose up -d --build
```

---

## Spec coverage check

| Spec section | Plan task(s) |
|---|---|
| `Conversation.metadata` for autonomy override | Task 1 |
| `ChatAutonomyService` + API | Task 2 |
| `JobChatNotifier` stage messages | Task 3 |
| New chat tools (`present_job_draft`, `set_chat_autonomy`) | Task 4 |
| Autonomy-aware orchestrator | Task 4 |
| Frontend `job_card` components | Task 5 |
| Resume/async via existing WebSocket | Tasks 3, 5 |
| User settings default | Task 6 |
| Phase 1 read-only / Phase 2 editing | Phase 2 not in this plan; phase 1 covers read-only review cards |

## Placeholder scan

- No `TBD` or `TODO` items.
- No vague "add error handling" steps; specific endpoints and actions are listed.
- No unspecified types; `AutonomyMode`, `JobCardAttachment`, and card props are defined.

## Type consistency check

- `ChatAutonomyService.get_mode`/`set_mode` accept `UUID` conversation/user IDs consistently.
- `JobChatNotifier` uses `str(job.id)` for `job_id` in attachments.
- Frontend `JobCardAttachment.job_id` is `string | null` matching the backend payload.
- `present_job_draft` returns `{"kind": "job_draft", "draft": {...}}`; frontend `JobDraftCard` expects that shape.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-13-card-driven-chat-media-creation.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach would you like?