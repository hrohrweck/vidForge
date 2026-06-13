"""Post interactive job-card attachments into the chat conversation."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.websocket import manager as ws_manager
from app.database import Conversation, Job, Message, VideoScene
from app.services.chat_autonomy_service import ChatAutonomyService
from app.storage import get_storage_backend

logger = logging.getLogger(__name__)


class JobChatNotifier:
    """Publish pipeline stage cards as chat message attachments."""

    @staticmethod
    async def _should_skip_intermediate(db: AsyncSession, job: Job) -> bool:
        """Return True when intermediate stage cards should be suppressed."""
        if job.chat_conversation_id is None:
            return True

        try:
            result = await db.execute(
                select(Conversation.user_id).where(
                    Conversation.id == job.chat_conversation_id
                )
            )
            user_id: UUID | None = result.scalar_one_or_none()
            if user_id is None:
                # Anonymous conversation: treat as confirm mode.
                return False

            mode = await ChatAutonomyService.get_mode(
                db, job.chat_conversation_id, user_id
            )
            return mode == "autonomous"
        except Exception:
            logger.warning(
                "Failed to resolve chat autonomy for job %s; defaulting to confirm",
                job.id,
                exc_info=True,
            )
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
        """Persist an assistant message with a single job_card attachment."""
        if job.chat_conversation_id is None:
            return

        message = Message(
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
    async def _load_scenes(db: AsyncSession, job: Job) -> list[VideoScene]:
        """Load all scenes for a job ordered by scene number."""
        result = await db.execute(
            select(VideoScene)
            .where(VideoScene.job_id == job.id)
            .order_by(VideoScene.scene_number)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _url_for(path: str | None) -> str | None:
        """Return a public URL for a storage path, or None."""
        if not path:
            return None
        try:
            return await get_storage_backend().get_url(path)
        except Exception:
            logger.warning("Failed to generate URL for path %s", path, exc_info=True)
            return None

    @staticmethod
    async def notify_planned(db: AsyncSession, job: Job) -> None:
        """Post a scene-plan review card."""
        if await JobChatNotifier._should_skip_intermediate(db, job):
            return

        scenes = await JobChatNotifier._load_scenes(db, job)
        data: dict[str, Any] = {
            "scenes": [
                {
                    "scene_number": scene.scene_number,
                    "start_time": scene.start_time,
                    "end_time": scene.end_time,
                    "visual_description": scene.visual_description,
                    "image_prompt": scene.image_prompt,
                    "mood": scene.mood,
                    "camera_movement": scene.camera_movement,
                }
                for scene in scenes
            ]
        }

        await JobChatNotifier._post_card(
            db,
            job,
            card_type="scene_plan",
            title=f"Scene plan for {job.title}",
            data=data,
            actions=["generate_images"],
            content=f"Planned {len(scenes)} scene(s) for **{job.title}**. "
            "Review them and click Generate images to continue.",
        )

    @staticmethod
    async def notify_images_ready(db: AsyncSession, job: Job) -> None:
        """Post an image-review card with thumbnail URLs."""
        if await JobChatNotifier._should_skip_intermediate(db, job):
            return

        scenes = await JobChatNotifier._load_scenes(db, job)
        data: dict[str, Any] = {
            "scenes": [
                {
                    "scene_number": scene.scene_number,
                    "thumbnail_url": await JobChatNotifier._url_for(
                        scene.thumbnail_path
                    ),
                    "status": scene.status,
                }
                for scene in scenes
            ]
        }

        await JobChatNotifier._post_card(
            db,
            job,
            card_type="image_review",
            title=f"Reference images for {job.title}",
            data=data,
            actions=["generate_videos"],
            content=f"Reference images are ready for **{job.title}**. "
            "Click Generate videos to continue.",
        )

    @staticmethod
    async def notify_videos_ready(db: AsyncSession, job: Job) -> None:
        """Post a video-review card with preview URLs."""
        if await JobChatNotifier._should_skip_intermediate(db, job):
            return

        scenes = await JobChatNotifier._load_scenes(db, job)
        data: dict[str, Any] = {
            "scenes": [
                {
                    "scene_number": scene.scene_number,
                    "preview_url": await JobChatNotifier._url_for(
                        scene.generated_video_path
                    ),
                    "status": scene.status,
                }
                for scene in scenes
            ]
        }

        await JobChatNotifier._post_card(
            db,
            job,
            card_type="video_review",
            title=f"Video clips for {job.title}",
            data=data,
            actions=["export"],
            content=f"Video clips are ready for **{job.title}**. "
            "Click Export to render the final video.",
        )

    @staticmethod
    async def notify_completed(db: AsyncSession, job: Job) -> None:
        """Post the final completion card."""
        data: dict[str, Any] = {
            "output_url": await JobChatNotifier._url_for(job.output_path),
            "preview_url": await JobChatNotifier._url_for(job.preview_path),
            "thumbnail_url": await JobChatNotifier._url_for(job.thumbnail_path),
        }

        await JobChatNotifier._post_card(
            db,
            job,
            card_type="job_completed",
            title=f"{job.title} is ready",
            data=data,
            actions=["download"],
            content=f"Your video **{job.title}** is ready.",
        )

    @staticmethod
    async def notify_failed(
        db: AsyncSession, job: Job, error_message: str
    ) -> None:
        """Post a failure card."""
        await JobChatNotifier._post_card(
            db,
            job,
            card_type="job_error",
            title=f"{job.title} failed",
            data={"error_message": error_message},
            actions=["retry", "cancel"],
            content=f"Sorry, **{job.title}** could not be completed: {error_message}",
        )
