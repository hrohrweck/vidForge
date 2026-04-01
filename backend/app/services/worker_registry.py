from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Worker, Provider


class WorkerRegistry:
    HEARTBEAT_TIMEOUT_SECONDS = 90

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self,
        worker_id: str,
        name: str,
        provider_id: UUID,
        capabilities: dict[str, Any] | None = None,
    ) -> Worker:
        result = await self.db.execute(select(Worker).where(Worker.worker_id == worker_id))
        worker = result.scalar_one_or_none()

        if worker:
            worker.name = name
            worker.capabilities = capabilities or {}
            worker.status = "online"
            worker.last_heartbeat = datetime.utcnow()
            worker.provider_id = provider_id
        else:
            worker = Worker(
                worker_id=worker_id,
                name=name,
                provider_id=provider_id,
                capabilities=capabilities or {},
                status="online",
                last_heartbeat=datetime.utcnow(),
            )
            self.db.add(worker)

        await self.db.commit()
        await self.db.refresh(worker)
        return worker

    async def heartbeat(self, worker_id: str) -> bool:
        result = await self.db.execute(select(Worker).where(Worker.worker_id == worker_id))
        worker = result.scalar_one_or_none()

        if not worker:
            return False

        worker.last_heartbeat = datetime.utcnow()
        await self.db.commit()
        return True

    async def set_status(self, worker_id: str, status: str, job_id: UUID | None = None) -> None:
        result = await self.db.execute(select(Worker).where(Worker.worker_id == worker_id))
        worker = result.scalar_one_or_none()

        if worker:
            worker.status = status
            worker.current_job_id = job_id
            await self.db.commit()

    async def get_worker(self, worker_id: str) -> Worker | None:
        result = await self.db.execute(select(Worker).where(Worker.worker_id == worker_id))
        return result.scalar_one_or_none()

    async def get_available_workers(
        self,
        provider_type: str | None = None,
        provider_id: UUID | None = None,
    ) -> list[Worker]:
        cutoff = datetime.utcnow() - timedelta(seconds=self.HEARTBEAT_TIMEOUT_SECONDS)

        query = select(Worker).where(
            and_(Worker.status == "online", Worker.last_heartbeat > cutoff)
        )

        if provider_id:
            query = query.where(Worker.provider_id == provider_id)
        elif provider_type:
            query = query.join(Provider).where(
                and_(Provider.provider_type == provider_type, Provider.is_active == True)
            )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all_workers(self, provider_id: UUID | None = None) -> list[Worker]:
        query = select(Worker)
        if provider_id:
            query = query.where(Worker.provider_id == provider_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def cleanup_stale_workers(self) -> int:
        cutoff = datetime.utcnow() - timedelta(seconds=self.HEARTBEAT_TIMEOUT_SECONDS)

        result = await self.db.execute(
            select(Worker).where(and_(Worker.status != "offline", Worker.last_heartbeat < cutoff))
        )
        stale = list(result.scalars().all())

        for worker in stale:
            worker.status = "offline"
            worker.current_job_id = None

        await self.db.commit()
        return len(stale)

    async def unregister(self, worker_id: str) -> bool:
        result = await self.db.execute(select(Worker).where(Worker.worker_id == worker_id))
        worker = result.scalar_one_or_none()

        if worker:
            await self.db.delete(worker)
            await self.db.commit()
            return True
        return False

    async def get_worker_count(self, provider_id: UUID | None = None) -> dict[str, int]:
        workers = await self.get_all_workers(provider_id)

        cutoff = datetime.utcnow() - timedelta(seconds=self.HEARTBEAT_TIMEOUT_SECONDS)

        return {
            "total": len(workers),
            "online": len(
                [
                    w
                    for w in workers
                    if w.status == "online" and w.last_heartbeat and w.last_heartbeat > cutoff
                ]
            ),
            "busy": len([w for w in workers if w.status == "busy"]),
            "offline": len(
                [
                    w
                    for w in workers
                    if w.status == "offline" or not w.last_heartbeat or w.last_heartbeat <= cutoff
                ]
            ),
        }
