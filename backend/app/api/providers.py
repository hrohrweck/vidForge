from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.database import get_db, Provider, User
from app.services.job_router import JobRouter
from app.services.worker_registry import WorkerRegistry
from app.services.budget_tracker import BudgetTracker


router = APIRouter(tags=["providers"])


class ProviderConfigBase(BaseModel):
    pass


class ComfyUIDirectProviderConfig(ProviderConfigBase):
    comfyui_url: str
    max_concurrent_jobs: int = 1


class RunPodProviderConfig(ProviderConfigBase):
    api_key: str
    endpoint_id: str
    cost_per_gpu_hour: float = 0.69
    idle_timeout_seconds: int = 30
    flashboot_enabled: bool = True
    max_workers: int = 3


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    provider_type: str = Field(..., pattern="^(comfyui_direct|runpod)$")
    config: dict[str, Any]
    daily_budget_limit: float | None = None
    priority: int = 0


class ProviderUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    daily_budget_limit: float | None = None
    priority: int | None = None
    is_active: bool | None = None


class ProviderResponse(BaseModel):
    id: UUID
    name: str
    provider_type: str
    config: dict[str, Any]
    is_active: bool
    daily_budget_limit: float | None
    current_daily_spend: float
    priority: int
    created_at: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
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

    config = data.config
    if data.provider_type == "comfyui_direct":
        ComfyUIDirectProviderConfig(**config)
    elif data.provider_type == "runpod":
        RunPodProviderConfig(**config)

    provider = Provider(
        name=data.name,
        provider_type=data.provider_type,
        config=config,
        daily_budget_limit=Decimal(str(data.daily_budget_limit))
        if data.daily_budget_limit
        else None,
        priority=data.priority,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
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
        provider.config = data.config
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


@router.get("/{provider_id}/status", response_model=ProviderStatusResponse)
async def get_provider_status(
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    router = JobRouter(db)
    registry = WorkerRegistry(db)
    status = await router.get_provider_status(provider_id)
    worker_count = await registry.get_worker_count(provider_id)

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
    provider_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    registry = WorkerRegistry(db)
    workers = await registry.get_all_workers(provider_id)
    return workers


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


@router.get("/status", response_model=list[ProviderStatusResponse])
async def list_providers_status(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
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
