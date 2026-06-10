from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AvatarAssignment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    avatar_id: UUID
    role: str | None = None
    consistency_strategy_override: str | None = None


class ModelPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    image_model: str | None = None
    video_model: str | None = None
    text_model: str | None = None
