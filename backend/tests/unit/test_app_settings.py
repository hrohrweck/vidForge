import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSetting
from app.services.app_settings import clear_settings_cache, get_setting, set_setting


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.mark.asyncio
async def test_get_setting_returns_default_when_missing(db_session: AsyncSession):
    value = await get_setting(db_session, "media.max_folder_depth", 9)

    assert value == 3


@pytest.mark.asyncio
async def test_set_setting_persists_and_invalidates_cache(db_session: AsyncSession, superuser):
    assert await get_setting(db_session, "media.max_folder_depth", 3) == 3

    setting = await set_setting(
        db_session,
        "media.max_folder_depth",
        5,
        updated_by=superuser.id,
    )

    assert setting.value == 5
    assert setting.updated_by == superuser.id
    assert await get_setting(db_session, "media.max_folder_depth", 3) == 5

    result = await db_session.execute(
        select(AppSetting).where(AppSetting.key == "media.max_folder_depth")
    )
    persisted = result.scalar_one()
    assert persisted.value == 5
