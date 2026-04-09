import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Provider, Job, Worker
from app.services.providers.base import ComfyUIProvider, ProviderInfo
from app.services.providers.comfyui_direct import ComfyUIDirectProvider
from app.services.providers.poe import PoeProvider
from app.services.providers.runpod import RunPodProvider
from app.services.worker_registry import WorkerRegistry
from app.services.budget_tracker import BudgetTracker


class JobRouterError(Exception):
    pass


class JobRouter:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.worker_registry = WorkerRegistry(db)
        self.budget_tracker = BudgetTracker(db)
        self._providers: dict[UUID, ComfyUIProvider] = {}

    async def get_provider_instance(self, provider_id: UUID) -> ComfyUIProvider:
        if provider_id in self._providers:
            return self._providers[provider_id]

        result = await self.db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()

        if not provider:
            raise JobRouterError(f"Provider {provider_id} not found")

        instance = await self._create_provider_instance(provider)
        self._providers[provider_id] = instance
        return instance

    async def _create_provider_instance(self, provider: Provider) -> ComfyUIProvider:
        if provider.provider_type == "comfyui_direct":
            instance = ComfyUIDirectProvider(provider.id, provider.config)
        elif provider.provider_type == "runpod":
            instance = RunPodProvider(provider.id, provider.config)
        elif provider.provider_type == "poe":
            instance = PoeProvider(provider.id, provider.config)
        else:
            raise JobRouterError(f"Unknown provider type: {provider.provider_type}")

        await instance.initialize(provider.config)
        return instance

    async def get_provider_record(self, provider_id: UUID) -> Provider | None:
        result = await self.db.execute(select(Provider).where(Provider.id == provider_id))
        return result.scalar_one_or_none()

    async def select_provider(
        self,
        preference: str = "auto",
        workflow: dict[str, Any] | None = None,
    ) -> tuple[Provider, ComfyUIProvider, str]:
        # If preference is a UUID, use that specific provider
        try:
            provider_id = UUID(preference)
            result = await self.db.execute(
                select(Provider).where(Provider.id == provider_id, Provider.is_active == True)
            )
            provider = result.scalar_one_or_none()
            if provider:
                instance = await self.get_provider_instance(provider.id)
                return provider, instance, f"Provider {provider.name} selected by ID"
        except ValueError:
            pass
        
        result = await self.db.execute(
            select(Provider).where(Provider.is_active == True).order_by(Provider.priority.desc())
        )
        providers = list(result.scalars().all())

        if not providers:
            raise JobRouterError("No providers configured")

        if preference == "comfyui_direct":
            for p in providers:
                if p.provider_type == "comfyui_direct":
                    instance = await self.get_provider_instance(p.id)
                    return p, instance, "ComfyUI Direct provider selected"
            raise JobRouterError("No ComfyUI Direct provider configured")

        if preference == "runpod":
            for p in providers:
                if p.provider_type == "runpod":
                    instance = await self.get_provider_instance(p.id)
                    estimated_cost = Decimal(str(await instance.estimate_cost(workflow or {})))
                    allowed, reason = await self.budget_tracker.check_budget(p.id, estimated_cost)
                    if allowed:
                        return p, instance, "RunPod provider selected"
                    raise JobRouterError(f"RunPod not available: {reason}")
            raise JobRouterError("No RunPod provider configured")

        comfyui_direct_available = False
        for p in providers:
            if p.provider_type == "comfyui_direct" and p.is_active:
                workers = await self.worker_registry.get_available_workers("comfyui_direct", p.id)
                if workers:
                    instance = await self.get_provider_instance(p.id)
                    return p, instance, "ComfyUI Direct provider available (free)"
                comfyui_direct_available = True

        for p in providers:
            if p.provider_type == "runpod" and p.is_active:
                instance = await self.get_provider_instance(p.id)
                estimated_cost = Decimal(str(await instance.estimate_cost(workflow or {})))
                allowed, reason = await self.budget_tracker.check_budget(p.id, estimated_cost)
                if allowed:
                    if comfyui_direct_available:
                        return p, instance, "RunPod selected (comfyui_direct workers busy)"
                    return p, instance, "RunPod selected"

        if comfyui_direct_available:
            raise JobRouterError("ComfyUI Direct provider busy and no cloud providers available")

        raise JobRouterError("No available providers")

    async def execute_job(
        self,
        job: Job,
        workflow: dict[str, Any],
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        if not job.provider_id:
            raise JobRouterError("Job has no provider assigned")

        provider = await self.get_provider_record(job.provider_id)
        if not provider:
            raise JobRouterError(f"Provider {job.provider_id} not found")

        provider_instance = await self.get_provider_instance(provider.id)

        start_time = datetime.utcnow()

        try:
            run_id = await provider_instance.queue_prompt(workflow)

            result = await provider_instance.wait_for_completion(
                run_id,
                progress_callback=progress_callback,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            if provider.provider_type == "runpod":
                actual_cost = await provider_instance.estimate_cost(workflow)
                await self.budget_tracker.record_spend(
                    provider.id,
                    job.id,
                    Decimal(str(actual_cost)),
                    duration_seconds=int(duration),
                    gpu_type=provider.config.get("gpu_type"),
                )

                job.actual_cost = Decimal(str(actual_cost))

            job.started_at = start_time
            job.completed_at = datetime.utcnow()
            await self.db.commit()

            return result

        except asyncio.TimeoutError:
            await provider_instance.cancel_job(str(job.id))
            raise JobRouterError(f"Provider '{provider.name}' timed out")
        except Exception as e:
            raise JobRouterError(f"Provider '{provider.name}' failed: {str(e)}")

    async def get_provider_status(self, provider_id: UUID) -> ProviderInfo:
        instance = await self.get_provider_instance(provider_id)
        return await instance.get_status()

    async def get_all_providers_status(self) -> list[dict[str, Any]]:
        result = await self.db.execute(select(Provider).where(Provider.is_active == True))
        providers = list(result.scalars().all())

        statuses = []
        for provider in providers:
            try:
                instance = await self.get_provider_instance(provider.id)
                info = await instance.get_status()
                worker_count = await self.worker_registry.get_worker_count(provider.id)

                statuses.append(
                    {
                        "id": str(provider.id),
                        "name": provider.name,
                        "type": provider.provider_type,
                        "is_available": info.is_available,
                        "estimated_wait_seconds": info.estimated_wait_seconds,
                        "message": info.message,
                        "workers": worker_count,
                        "daily_budget_limit": float(provider.daily_budget_limit)
                        if provider.daily_budget_limit
                        else None,
                        "current_daily_spend": float(provider.current_daily_spend),
                    }
                )
            except Exception as e:
                statuses.append(
                    {
                        "id": str(provider.id),
                        "name": provider.name,
                        "type": provider.provider_type,
                        "is_available": False,
                        "message": f"Error: {str(e)}",
                    }
                )

        return statuses

    async def estimate_job_cost(
        self, provider_id: UUID, workflow: dict[str, Any]
    ) -> dict[str, Any]:
        instance = await self.get_provider_instance(provider_id)
        cost = await instance.estimate_cost(workflow)
        duration = await instance.estimate_duration(workflow)

        return {
            "estimated_cost": cost,
            "estimated_duration_seconds": duration,
            "provider_type": (await self.get_provider_record(provider_id)).provider_type,
        }

    async def shutdown(self) -> None:
        for provider_instance in self._providers.values():
            try:
                await provider_instance.shutdown()
            except Exception:
                pass
        self._providers.clear()
