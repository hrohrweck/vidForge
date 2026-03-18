from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.database import User, UserSettings, get_db

router = APIRouter()


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None


class UserSettingsResponse(BaseModel):
    default_style_id: str | None = None
    storage_backend: str = "local"
    storage_config: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    default_style_id: str | None = None
    storage_backend: str | None = None
    storage_config: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


@router.get("/me", response_model=UserResponse)
async def get_user_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/settings", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettings:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings


@router.put("/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    settings_data: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettings:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    if settings_data.default_style_id is not None:
        from uuid import UUID

        settings.default_style_id = UUID(settings_data.default_style_id)
    if settings_data.storage_backend is not None:
        settings.storage_backend = settings_data.storage_backend
    if settings_data.storage_config is not None:
        settings.storage_config = settings_data.storage_config
    if settings_data.preferences is not None:
        settings.preferences = settings_data.preferences

    await db.commit()
    await db.refresh(settings)

    return settings
