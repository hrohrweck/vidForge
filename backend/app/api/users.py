from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user_from_bearer_or_cookie
from app.database import ModelConfig, User, UserSettings, get_db

router = APIRouter()


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None


class UserSettingsResponse(BaseModel):
    default_style_id: str | None = None
    storage_backend: str = "local"
    storage_config: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class UserSettingsUpdate(BaseModel):
    default_style_id: str | None = None
    storage_backend: str | None = None
    storage_config: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


@router.get("/me", response_model=UserResponse)
async def get_user_me(current_user: User = Depends(get_current_user_from_bearer_or_cookie)) -> User:
    return current_user


@router.get("/settings", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
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
        merged = dict(settings.preferences or {})
        merged.update(settings_data.preferences)
        settings.preferences = merged

    await db.commit()
    await db.refresh(settings)

    return settings


class ChatModelRequest(BaseModel):
    default_chat_model: str


class ChatModelResponse(BaseModel):
    default_chat_model: str | None = None


@router.get("/settings/chat-model", response_model=ChatModelResponse)
async def get_chat_model(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ChatModelResponse:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings or not settings.preferences:
        return ChatModelResponse(default_chat_model=None)

    return ChatModelResponse(default_chat_model=settings.preferences.get("default_chat_model"))


@router.put("/settings/chat-model", response_model=ChatModelResponse)
async def update_chat_model(
    data: ChatModelRequest,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ChatModelResponse:
    from sqlalchemy.orm import selectinload

    # Validate the model exists and is chat-enabled
    result = await db.execute(
        select(ModelConfig)
        .options(selectinload(ModelConfig.provider))
        .where(
            ModelConfig.model_id == data.default_chat_model,
            ModelConfig.is_active == True,  # noqa: E712
            ModelConfig.is_chat_enabled == True,  # noqa: E712
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"Model '{data.default_chat_model}' is not a valid chat-enabled model",
        )

    # Get or create user settings
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    # Store in preferences
    current_prefs = dict(settings.preferences) if settings.preferences else {}
    current_prefs["default_chat_model"] = data.default_chat_model
    settings.preferences = current_prefs

    await db.commit()
    return ChatModelResponse(default_chat_model=data.default_chat_model)


class SidebarSettingsRequest(BaseModel):
    sidebar_open: bool


class SidebarSettingsResponse(BaseModel):
    sidebar_open: bool


@router.get("/settings/sidebar", response_model=SidebarSettingsResponse)
async def get_sidebar_settings(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> SidebarSettingsResponse:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings or not settings.preferences:
        return SidebarSettingsResponse(sidebar_open=True)

    ui_prefs = settings.preferences.get("ui")
    if isinstance(ui_prefs, dict):
        return SidebarSettingsResponse(sidebar_open=ui_prefs.get("sidebar_open", True))

    return SidebarSettingsResponse(sidebar_open=True)


@router.put("/settings/sidebar", response_model=SidebarSettingsResponse)
async def update_sidebar_settings(
    data: SidebarSettingsRequest,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> SidebarSettingsResponse:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    current_prefs = dict(settings.preferences) if settings.preferences else {}
    ui_prefs = dict(current_prefs.get("ui") or {}) if isinstance(current_prefs.get("ui"), dict) else {}
    ui_prefs["sidebar_open"] = data.sidebar_open
    current_prefs["ui"] = ui_prefs
    settings.preferences = current_prefs

    await db.commit()
    return SidebarSettingsResponse(sidebar_open=data.sidebar_open)


class ChatAutonomyRequest(BaseModel):
    chat_autonomy: Literal["confirm", "autonomous"]


class ChatAutonomyResponse(BaseModel):
    chat_autonomy: Literal["confirm", "autonomous"] | None = None


@router.get("/settings/chat-autonomy", response_model=ChatAutonomyResponse)
async def get_chat_autonomy(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ChatAutonomyResponse:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if not settings or not settings.preferences:
        return ChatAutonomyResponse(chat_autonomy=None)

    return ChatAutonomyResponse(chat_autonomy=settings.preferences.get("chat_autonomy"))


@router.put("/settings/chat-autonomy", response_model=ChatAutonomyResponse)
async def update_chat_autonomy(
    data: ChatAutonomyRequest,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
    db: AsyncSession = Depends(get_db),
) -> ChatAutonomyResponse:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    current_prefs = dict(settings.preferences) if settings.preferences else {}
    current_prefs["chat_autonomy"] = data.chat_autonomy
    settings.preferences = current_prefs

    await db.commit()
    await db.refresh(settings)
    return ChatAutonomyResponse(chat_autonomy=data.chat_autonomy)
