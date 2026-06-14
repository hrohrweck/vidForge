from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Conversation, UserSettings

AutonomyMode = Literal["confirm", "autonomous"]
DEFAULT_MODE: AutonomyMode = "confirm"


class ChatAutonomyService:
    """Manage per-conversation chat autonomy mode overrides."""

    @staticmethod
    async def get_default_mode(db: AsyncSession, user_id: UUID) -> AutonomyMode:
        """Return the user's default chat autonomy preference, or ``confirm``."""
        result = await db.execute(
            select(UserSettings.preferences).where(UserSettings.user_id == user_id)
        )
        preferences = result.scalar_one_or_none()
        if preferences:
            value = preferences.get("chat_autonomy")
            if value in ("confirm", "autonomous"):
                return value  # type: ignore[return-value]
        return DEFAULT_MODE

    @staticmethod
    async def get_mode(
        db: AsyncSession, conversation_id: UUID, user_id: UUID
    ) -> AutonomyMode:
        """Return the autonomy mode for a conversation, falling back to the user default."""
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError("Conversation not found")

        metadata = conversation.metadata_ or {}
        value = metadata.get("chat_autonomy")
        if value in ("confirm", "autonomous"):
            return value  # type: ignore[return-value]
        return await ChatAutonomyService.get_default_mode(db, user_id)

    @staticmethod
    async def set_mode(
        db: AsyncSession, conversation_id: UUID, user_id: UUID, mode: AutonomyMode
    ) -> AutonomyMode:
        """Set the autonomy mode override for a conversation owned by ``user_id``."""
        if mode not in ("confirm", "autonomous"):
            raise ValueError(f"Invalid autonomy mode: {mode}")

        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError("Conversation not found")

        metadata = conversation.metadata_ or {}
        metadata["chat_autonomy"] = mode
        conversation.metadata_ = metadata
        await db.commit()
        await db.refresh(conversation)
        return mode
