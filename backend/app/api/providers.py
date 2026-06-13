from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_from_bearer_or_cookie, require_admin
from app.database import ModelConfig, Provider, User, get_db
from app.services.budget_tracker import BudgetTracker
from app.services.job_router import JobRouter
from app.services.model_config_service import ModelConfigService
from app.services.providers import registry
from app.services.worker_registry import WorkerRegistry

router = APIRouter(tags=["providers"])


# ── Provider Schemas ──────────────────────────────────────────────


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    provider_type: str = Field(..., min_length=1)
    config: dict[str, Any]
    daily_budget_limit: float | None = None
    priority: int = 0


class ProviderUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    daily_budget_limit: float | None = None
    priority: int | None = None
    is_active: bool | None = None


SENSITIVE_CONFIG_KEYS = {"api_key", "secret", "token", "password"}
MASK_SENTINEL = "***"


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive values in a provider/storage config dict."""
    redacted = {}
    for key, value in config.items():
        if any(sensitive in key.lower() for sensitive in SENSITIVE_CONFIG_KEYS):
            redacted[key] = MASK_SENTINEL
        else:
            redacted[key] = value
    return redacted


class ProviderResponse(BaseModel):
    id: UUID
    name: str
    provider_type: str
    config: dict[str, Any]
    is_active: bool
    daily_budget_limit: float | None
    current_daily_spend: float
    priority: int
    redirect_url: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("config")
    def serialize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return redact_config(config)


class ProviderStatusResponse(BaseModel):
    id: UUID
    name: str
    type: str
    is_available: bool
    estimated_wait_seconds: float
    message: str
    workers: dict[str, int] | None
    daily_budget_limit: float | None
    current_daily_spend: float


class WorkerResponse(BaseModel):
    id: UUID
    worker_id: str
    name: str
    status: str
    capabilities: dict[str, Any]
    last_heartbeat: datetime | None
    current_job_id: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Model Schemas ─────────────────────────────────────────────────


class ModelConfigCreate(BaseModel):
    """Schema for creating a model configuration entry."""
    model_id: str = Field(..., min_length=1, max_length=255)
    provider_model_id: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=200)
    modality: str = Field(..., pattern=r"^(video|image|text)$")
    endpoint_type: str = Field(default="comfyui")
    prompt_format: str = Field(default="string")
    parameter_map: dict[str, Any] | None = None
    extra_params: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    cost_config: dict[str, Any] | None = None
    comfyui_workflow: str | None = None
    is_active: bool = True


class ModelConfigUpdate(BaseModel):
    """Schema for updating a model configuration entry."""
    model_id: str | None = Field(None, min_length=1, max_length=255)
    provider_model_id: str | None = Field(None, min_length=1, max_length=200)
    display_name: str | None = None
    modality: str | None = Field(None, pattern=r"^(video|image|text)$")
    endpoint_type: str | None = None
    prompt_format: str | None = None
    parameter_map: dict[str, Any] | None = None
    extra_params: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    cost_config: dict[str, Any] | None = None
    comfyui_workflow: str | None = None
    is_active: bool | None = None


class ModelConfigResponse(BaseModel):
    id: UUID
    provider_id: UUID
    model_id: str
    provider_model_id: str
    display_name: str
    modality: str
    endpoint_type: str
    prompt_format: str
    is_active: bool
    is_deprecated: bool
    last_synced_at: datetime | None
    created_at: datetime
    cost_config: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class SyncModelsResponse(BaseModel):
    provider_id: UUID
    synced_count: int
    models: list[ModelConfigResponse]


# ── Provider Status ───────────────────────────────────────────────


@router.get("/status", response_model=list[ProviderStatusResponse])
async def list_providers_status(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user_from_bearer_or_cookie)
):
    router = JobRouter(db)
    statuses = await router.get_all_providers_status()

    result = await db.execute(select(Provider))
    providers = {str(p.id): p for p in result.scalars().all()}

    response = []
    for status in statuses:
        provider = providers.get(status["id"])
        if provider:
            response.append(
                ProviderStatusResponse(
                    id=UUID(status["id"]),
                    name=status["name"],
                    type=status["type"],
                    is_available=status.get("is_available", False),
                    estimated_wait_seconds=status.get("estimated_wait_seconds", 0),
                    message=status.get("message", ""),
                    workers=status.get("workers"),
                    daily_budget_limit=float(provider.daily_budget_limit)
                    if provider.daily_budget_limit
                    else None,
                    current_daily_spend=float(provider.current_daily_spend),
                )
            )

    return response


# ── Provider CRUD ─────────────────────────────────────────────────


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user_from_bearer_or_cookie)
):
    result = await db.execute(select(Provider).order_by(Provider.priority.desc()))
    return list(result.scalars().all())


@router.post("", response_model=ProviderResponse)
async def create_provider(
    data: ProviderCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
):
    existing = await db.execute(select(Provider).where(Provider.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Provider with this name already exists")

    # Validate provider_type against the registry
    if not registry.has(data.provider_type):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider type: {data.provider_type}",
        )

    provider = Provider(
        name=data.name,
        provider_type=data.provider_type,
        config=data.config,
        daily_budget_limit=Decimal(str(data.daily_budget_limit))
        if data.daily_budget_limit
        else None,
        priority=data.priority,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    resp = ProviderResponse.model_validate(provider)
    resp.redirect_url = f"/admin/models?provider={provider.id}"
    return resp


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user_from_bearer_or_cookie)
):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.patch("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: UUID,
    data: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if data.name is not None:
        provider.name = data.name
    if data.config is not None:
        # Merge with existing config so sensitive fields (api_key) aren't
        # wiped when the client sends a partial config
        merged = {**provider.config, **data.config}
        # Remove empty strings that indicate "keep existing"
        merged = {k: v for k, v in merged.items() if v != ""}
        # Restore existing values for sensitive keys when the client sends
        # the mask sentinel, so admin UI round-trips don't overwrite real
        # secrets with the redacted placeholder.
        for key in list(merged.keys()):
            if (
                any(sensitive in key.lower() for sensitive in SENSITIVE_CONFIG_KEYS)
                and merged[key] == MASK_SENTINEL
                and key in provider.config
            ):
                merged[key] = provider.config[key]
        provider.config = merged
    if data.daily_budget_limit is not None:
        provider.daily_budget_limit = Decimal(str(data.daily_budget_limit))
    if data.priority is not None:
        provider.priority = data.priority
    if data.is_active is not None:
        provider.is_active = data.is_active

    await db.commit()
    await db.refresh(provider)
    return provider


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.delete(provider)
    await db.commit()
    return {"status": "deleted"}


# ── Provider Status & Workers ──────────────────────────────────────


@router.get("/{provider_id}/status", response_model=ProviderStatusResponse)
async def get_provider_status(
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user_from_bearer_or_cookie)
):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    router = JobRouter(db)
    registry_ = WorkerRegistry(db)
    status = await router.get_provider_status(provider_id)
    worker_count = await registry_.get_worker_count(provider_id)

    return ProviderStatusResponse(
        id=provider.id,
        name=provider.name,
        type=provider.provider_type,
        is_available=status.is_available,
        estimated_wait_seconds=status.estimated_wait_seconds,
        message=status.message,
        workers=worker_count,
        daily_budget_limit=float(provider.daily_budget_limit)
        if provider.daily_budget_limit
        else None,
        current_daily_spend=float(provider.current_daily_spend),
    )


@router.get("/{provider_id}/workers", response_model=list[WorkerResponse])
async def list_provider_workers(
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user_from_bearer_or_cookie)
):
    registry_ = WorkerRegistry(db)
    workers = await registry_.get_all_workers(provider_id)
    return workers


# ── Budget ────────────────────────────────────────────────────────


@router.patch("/{provider_id}/budget")
async def update_provider_budget(
    provider_id: UUID,
    daily_budget_limit: float | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider.daily_budget_limit = Decimal(str(daily_budget_limit)) if daily_budget_limit else None
    await db.commit()
    return {"daily_budget_limit": daily_budget_limit}


@router.post("/{provider_id}/reset-spend")
async def reset_provider_spend(
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
):
    tracker = BudgetTracker(db)
    success = await tracker.reset_provider_spend(provider_id)
    if not success:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "reset"}


# ── Generic Model CRUD ────────────────────────────────────────────


@router.get("/{provider_id}/models", response_model=list[ModelConfigResponse])
async def list_provider_models(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_from_bearer_or_cookie),
):
    """List all model configurations for a provider."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")
    return await ModelConfigService.list_by_provider(db, provider_id, active_only=False)


@router.post("/{provider_id}/models", response_model=ModelConfigResponse)
async def create_provider_model(
    provider_id: UUID,
    data: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Create or update a model configuration for a provider."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    create_data = data.model_dump()
    create_data["provider_id"] = provider_id
    config = await ModelConfigService.get_or_create(
        db, provider_id, data.model_id, create_data
    )
    await db.commit()
    await db.refresh(config)
    return config


@router.patch("/{provider_id}/models/{model_id}", response_model=ModelConfigResponse)
async def update_provider_model(
    provider_id: UUID,
    model_id: UUID,
    data: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Update a model configuration entry."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")

    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_id,
            ModelConfig.provider_id == provider_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(config, key):
            setattr(config, key, value)

    await db.commit()
    await db.refresh(config)
    return config


@router.delete("/{provider_id}/models/{model_id}")
async def delete_provider_model(
    provider_id: UUID,
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Soft-delete a model configuration entry."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")

    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_id,
            ModelConfig.provider_id == provider_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")

    config.is_active = False
    await db.commit()
    return {"status": "deleted"}


# ── Model Sync ────────────────────────────────────────────────────


@router.post("/{provider_id}/sync-models", response_model=SyncModelsResponse)
async def sync_provider_models(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Synchronize live provider models into local ModelConfig entries."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    instance = await registry.create(
        provider.provider_type, provider.id, provider.config
    )
    try:
        models = await instance.sync_models()  # type: ignore[attr-defined]
    except NotImplementedError:
        raise HTTPException(
            status_code=400,
            detail=f"Provider type '{provider.provider_type}' does not support model sync",
        )
    finally:
        await instance.shutdown()

    # Persist synced models via ModelConfigService
    synced: list[ModelConfig] = []
    for model_data in models:
        model_id = model_data.get("model_id", model_data.get("id", ""))
        if not model_id:
            continue
        config = await ModelConfigService.upsert(
            db, provider_id, model_id, model_data
        )
        synced.append(config)

    await db.commit()
    return SyncModelsResponse(
        provider_id=provider_id,
        synced_count=len(synced),
        models=[ModelConfigResponse.model_validate(c) for c in synced],
    )
