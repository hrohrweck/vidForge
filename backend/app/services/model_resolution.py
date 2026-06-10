from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, Provider, UserSettings
from app.services.job_router import JobRouter


async def get_provider_instance(
    db: AsyncSession,
    provider: Provider,
) -> Any:
    """Return a cached provider instance for ``provider``.

    Thin wrapper around ``JobRouter.get_provider_instance()``. Kept as a
    public function for backward compatibility with existing callers and test
    mocking.
    """
    router = JobRouter(db)
    return await router.get_provider_instance(provider.id)


async def get_provider_for_job(
    db: AsyncSession,
    job: Job,
    modality: str,
) -> tuple[Provider | None, Any]:
    """Resolve an active provider instance for the given job and modality.

    Uses registry-based lookup — no longer hard-codes provider-type lists.
    Falls back to iterating all capable providers via JobRouter.
    """
    provider_id = job.image_provider_id if modality == "image" else job.video_provider_id
    router = JobRouter(db)

    if provider_id:
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()
        if provider and provider.is_active:
            instance = await router.get_provider_instance(provider.id)
            return provider, instance
        return None, None

    async for prov in router.iterate_providers():
        try:
            instance = await router.get_provider_instance(prov.id)
            # get_capabilities() is on ProviderBase — runtime instances
            # have it even though registry.create() returns ComfyUIProvider.
            caps = instance.get_capabilities()  # type: ignore[attr-defined]
            if modality == "image" and caps.supports_image:
                return prov, instance
            if modality == "video" and caps.supports_video:
                return prov, instance
        except Exception:
            continue

    return None, None


async def get_user_model_preferences(db: AsyncSession, user_id: UUID) -> dict[str, str]:
    """Get user's full model preferences from settings.

    Returns all granular and coarse model fields plus provider_id companions.
    Falls back to defaults for any missing fields.
    """
    from app.api.models import get_default_model_preferences

    defaults = await get_default_model_preferences(db)

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    user_settings = result.scalar_one_or_none()

    if not user_settings or not user_settings.preferences:
        return defaults

    model_prefs = user_settings.preferences.get("models", {})
    if not model_prefs:
        return defaults

    # Merge stored prefs over defaults, preserving all fields
    merged = dict(defaults)
    for key in defaults:
        if key in model_prefs:
            merged[key] = model_prefs[key]
    return merged


def select_model_for(prefs: dict[str, str], task: str) -> tuple[str, str]:
    """Select the appropriate model_id and provider_id for a given task.

    Args:
        prefs: Full preferences dict from get_user_model_preferences().
        task: One of "text_to_image", "image_to_image", "text_to_video",
              "image_to_video", "text".

    Returns:
        (model_id, provider_id) tuple. Falls back to coarse fields when
        granular fields are empty.
    """
    if task == "image_to_video":
        model = prefs.get("image_to_video_model", "")
        provider = prefs.get("image_to_video_provider_id", "")
        if model:
            return model, provider
        return prefs.get("video_model", "wan2.2"), prefs.get("video_provider_id", "")

    if task == "text_to_video":
        model = prefs.get("text_to_video_model", "")
        provider = prefs.get("text_to_video_provider_id", "")
        if model:
            return model, provider
        return prefs.get("video_model", "wan2.2"), prefs.get("video_provider_id", "")

    if task == "image_to_image":
        model = prefs.get("image_to_image_model", "")
        provider = prefs.get("image_to_image_provider_id", "")
        if model:
            return model, provider
        return prefs.get("image_model", "flux1-schnell"), prefs.get("image_provider_id", "")

    if task == "text_to_image":
        model = prefs.get("text_to_image_model", "")
        provider = prefs.get("text_to_image_provider_id", "")
        if model:
            return model, provider
        return prefs.get("image_model", "flux1-schnell"), prefs.get("image_provider_id", "")

    if task == "text":
        return prefs.get("text_model", "qwen3.6:35b"), prefs.get("text_provider_id", "")

    raise ValueError(f"Unknown task: {task}")
