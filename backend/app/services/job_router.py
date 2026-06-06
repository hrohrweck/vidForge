import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, Provider
from app.services.budget_tracker import BudgetTracker
from app.services.providers import registry
from app.services.providers.base import ComfyUIProvider, ProviderBase, ProviderInfo
from app.services.worker_registry import WorkerRegistry


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

        instance = await registry.create(
            provider.provider_type, provider.id, provider.config
        )
        self._providers[provider_id] = instance
        return instance

    async def get_provider_record(self, provider_id: UUID) -> Provider | None:
        result = await self.db.execute(select(Provider).where(Provider.id == provider_id))
        return result.scalar_one_or_none()

    async def iterate_providers(
        self,
        provider_types: list[str] | None = None,
        active_only: bool = True,
    ):
        query = select(Provider)
        if active_only:
            query = query.where(Provider.is_active == True)  # noqa: E712
        if provider_types:
            query = query.where(Provider.provider_type.in_(provider_types))
        query = query.order_by(Provider.priority.desc())
        result = await self.db.execute(query)
        for row in result.scalars():
            yield row

    async def select_provider(
        self,
        preference: str = "auto",
        workflow: dict[str, Any] | None = None,
        modality: str | None = None,
    ) -> tuple[Provider, ComfyUIProvider, str]:
        # If preference is a UUID, use that specific provider
        try:
            provider_id = UUID(preference)
            result = await self.db.execute(
                select(Provider).where(Provider.id == provider_id, Provider.is_active)
            )
            provider = result.scalar_one_or_none()
            if provider:
                instance = await self.get_provider_instance(provider.id)
                return provider, instance, f"Provider {provider.name} selected by ID"
        except ValueError:
            pass

        query = select(Provider).where(
            Provider.is_active
        ).order_by(Provider.priority.desc())

        if preference != "auto":
            query = query.where(Provider.provider_type == preference)

        result = await self.db.execute(query)
        providers = list(result.scalars().all())

        if not providers:
            raise JobRouterError("No providers configured")

        for p in providers:
            instance = await self.get_provider_instance(p.id)

            if modality:
                caps = cast(ProviderBase, instance).get_capabilities()
                if modality == "image" and not caps.supports_image:
                    continue
                if modality == "video" and not caps.supports_video:
                    continue

            # Workers registered = provider uses worker pool; none online = no capacity.
            # No workers registered (total == 0) = cloud/external provider, skip check.
            worker_counts = await self.worker_registry.get_worker_count(p.id)
            if worker_counts["total"] > 0 and worker_counts["online"] == 0:
                continue

            estimated_cost = await instance.estimate_cost(workflow or {})
            if estimated_cost > 0:
                cost_decimal = Decimal(str(estimated_cost))
                allowed, reason = await self.budget_tracker.check_budget(p.id, cost_decimal)
                if not allowed:
                    continue

            return p, instance, f"Provider {p.name} selected"

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

            actual_cost = await provider_instance.estimate_cost(workflow)
            if actual_cost > 0:
                await self.budget_tracker.record_spend(
                    provider.id,
                    job.id,
                    Decimal(str(actual_cost)),
                    duration_seconds=int(duration),
                    gpu_type=provider.config.get("gpu_type") if provider.config else None,
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
        result = await self.db.execute(select(Provider).where(Provider.is_active))
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

        record = await self.get_provider_record(provider_id)
        return {
            "estimated_cost": cost,
            "estimated_duration_seconds": duration,
            "provider_type": record.provider_type if record else None,
        }

    async def shutdown(self) -> None:
        for provider_instance in self._providers.values():
            try:
                await provider_instance.shutdown()
            except Exception:
                pass
        self._providers.clear()
