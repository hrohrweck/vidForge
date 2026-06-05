"""Application-wide settings service."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.app_settings import AppSetting
else:
    AppSetting = None

CACHE_TTL_SECONDS = 60
DEFAULT_SETTINGS: dict[str, Any] = {
    "media.max_folder_depth": 3,
    # Retention period (in days) for notification records before cleanup.
    # Type: integer, valid range 1-365.
    "notifications.retention_days": 30,
}

_cache: dict[str, tuple[Any, float]] = {}


def clear_settings_cache() -> None:
    _cache.clear()


async def get_setting(db: AsyncSession, key: str, default: Any = None) -> Any:
    from app.models.app_settings import AppSetting

    now = time.monotonic()
    cached = _cache.get(key)
    if cached and cached[1] > now:
        return cached[0]

    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    value = setting.value if setting else DEFAULT_SETTINGS.get(key, default)
    _cache[key] = (value, now + CACHE_TTL_SECONDS)
    return value


async def set_setting(
    db: AsyncSession,
    key: str,
    value: Any,
    updated_by: UUID | None = None,
) -> AppSetting:
    from app.models.app_settings import AppSetting

    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        setting.updated_by = updated_by
    else:
        setting = AppSetting(key=key, value=value, updated_by=updated_by)
        db.add(setting)

    await db.commit()
    await db.refresh(setting)
    _cache.pop(key, None)
    return setting
