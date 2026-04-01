from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from app.database import Provider, CostLog


class BudgetTracker:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_budget(self, provider_id: UUID, estimated_cost: Decimal) -> tuple[bool, str]:
        result = await self.db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()

        if not provider:
            return False, "Provider not found"

        await self._reset_if_needed(provider)

        if provider.daily_budget_limit is None:
            return True, "No budget limit configured"

        new_spend = provider.current_daily_spend + estimated_cost
        if new_spend > provider.daily_budget_limit:
            remaining = provider.daily_budget_limit - provider.current_daily_spend
            return (
                False,
                f"Daily budget exceeded. Remaining: ${remaining:.2f}, Estimated: ${estimated_cost:.2f}",
            )

        return True, "Within budget"

    async def record_spend(
        self,
        provider_id: UUID,
        job_id: UUID | None,
        amount: Decimal,
        duration_seconds: int | None = None,
        gpu_type: str | None = None,
    ) -> None:
        result = await self.db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()

        if not provider:
            return

        await self._reset_if_needed(provider)

        provider.current_daily_spend = provider.current_daily_spend + amount
        provider.updated_at = datetime.utcnow()

        log = CostLog(
            provider_id=provider_id,
            job_id=job_id,
            amount=amount,
            duration_seconds=duration_seconds,
            gpu_type=gpu_type,
        )
        self.db.add(log)
        await self.db.commit()

    async def _reset_if_needed(self, provider: Provider) -> None:
        now = datetime.utcnow()
        if provider.spend_reset_at.date() < now.date():
            provider.current_daily_spend = Decimal("0")
            provider.spend_reset_at = now

    async def get_daily_summary(self, provider_id: UUID | None = None) -> dict[str, Any]:
        today = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)

        query = select(
            CostLog.provider_id,
            func.sum(CostLog.amount).label("total_spend"),
            func.count(CostLog.id).label("job_count"),
        ).where(
            and_(
                CostLog.created_at >= datetime.combine(today, datetime.min.time()),
                CostLog.created_at < datetime.combine(tomorrow, datetime.min.time()),
            )
        )

        if provider_id:
            query = query.where(CostLog.provider_id == provider_id)

        query = query.group_by(CostLog.provider_id)

        result = await self.db.execute(query)
        rows = result.all()

        summaries = {}
        for row in rows:
            summaries[str(row.provider_id)] = {
                "total_spend": float(row.total_spend),
                "job_count": row.job_count,
            }

        if provider_id and str(provider_id) not in summaries:
            return {"total_spend": 0.0, "job_count": 0}

        return (
            summaries
            if not provider_id
            else summaries.get(str(provider_id), {"total_spend": 0.0, "job_count": 0})
        )

    async def get_provider_budget_status(self, provider_id: UUID) -> dict[str, Any]:
        result = await self.db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()

        if not provider:
            return {"error": "Provider not found"}

        await self._reset_if_needed(provider)

        daily_summary = await self.get_daily_summary(provider_id)

        return {
            "provider_id": str(provider_id),
            "provider_name": provider.name,
            "daily_budget_limit": float(provider.daily_budget_limit)
            if provider.daily_budget_limit
            else None,
            "current_daily_spend": float(provider.current_daily_spend),
            "remaining_budget": float(provider.daily_budget_limit - provider.current_daily_spend)
            if provider.daily_budget_limit
            else None,
            "jobs_today": daily_summary.get("job_count", 0),
            "spend_reset_at": provider.spend_reset_at.isoformat(),
        }

    async def reset_provider_spend(self, provider_id: UUID) -> bool:
        result = await self.db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()

        if not provider:
            return False

        provider.current_daily_spend = Decimal("0")
        provider.spend_reset_at = datetime.utcnow()
        await self.db.commit()
        return True

    async def get_cost_history(
        self,
        provider_id: UUID | None = None,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        start_date = datetime.utcnow() - timedelta(days=days)

        query = select(CostLog).where(CostLog.created_at >= start_date)

        if provider_id:
            query = query.where(CostLog.provider_id == provider_id)

        query = query.order_by(CostLog.created_at.desc())

        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return [
            {
                "id": str(log.id),
                "provider_id": str(log.provider_id),
                "job_id": str(log.job_id) if log.job_id else None,
                "amount": float(log.amount),
                "duration_seconds": log.duration_seconds,
                "gpu_type": log.gpu_type,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
