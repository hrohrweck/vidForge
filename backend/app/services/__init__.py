import asyncio
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import Job, Template

settings = get_settings()


class ComfyUIClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.comfyui_url
        self.client = httpx.AsyncClient(timeout=300.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def get_system_info(self) -> dict:
        """Get ComfyUI system info to check version and available nodes."""
        try:
            response = await self.client.get(f"{self.base_url}/system_stats")
            return response.json()
        except Exception:
            return {}

    async def queue_prompt(self, workflow: dict[str, Any]) -> dict:
        response = await self.client.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
        )
        if response.status_code >= 400:
            error_detail = response.text
            raise httpx.HTTPStatusError(
                f"ComfyUI error {response.status_code}: {error_detail}",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        return response.json()

    async def get_history(self, prompt_id: str) -> dict:
        response = await self.client.get(f"{self.base_url}/history/{prompt_id}")
        response.raise_for_status()
        return response.json()

    async def upload_file(self, file_path: str, file_data: bytes) -> str:
        response = await self.client.post(
            f"{self.base_url}/upload/image",
            files={"image": (file_path, file_data)},
        )
        response.raise_for_status()
        return response.json().get("name", file_path)

    async def get_output(self, filename: str, subfolder: str = "") -> bytes:
        params = {"filename": filename}
        if subfolder:
            params["subfolder"] = subfolder
            params["type"] = "output"

        response = await self.client.get(f"{self.base_url}/view", params=params)
        response.raise_for_status()
        return response.content

    async def wait_for_completion(
        self, prompt_id: str, poll_interval: float = 2.0, timeout: float = 600.0
    ) -> dict:
        elapsed = 0.0
        while elapsed < timeout:
            history = await self.get_history(prompt_id)
            if prompt_id in history:
                return history[prompt_id]
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")


class JobService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_job(self, job_id: UUID) -> Job | None:
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def get_user_jobs(
        self, user_id: UUID, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[Job]:
        query = select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc())
        if status:
            query = query.where(Job.status == status)
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_job(
        self, user_id: UUID, template_id: UUID | None = None, input_data: dict | None = None
    ) -> Job:
        job = Job(
            user_id=user_id,
            template_id=template_id,
            input_data=input_data or {},
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def update_job(
        self,
        job_id: UUID,
        status: str | None = None,
        progress: int | None = None,
        error_message: str | None = None,
        output_path: str | None = None,
        preview_path: str | None = None,
    ) -> Job | None:
        job = await self.get_job(job_id)
        if not job:
            return None

        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
        if error_message is not None:
            job.error_message = error_message
        if output_path is not None:
            job.output_path = output_path
        if preview_path is not None:
            job.preview_path = preview_path

        if status == "processing" and not job.started_at:
            job.started_at = datetime.utcnow()
        if status in ("completed", "failed") and not job.completed_at:
            job.completed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def delete_job(self, job_id: UUID) -> bool:
        job = await self.get_job(job_id)
        if not job:
            return False
        await self.db.delete(job)
        await self.db.commit()
        return True


class TemplateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_templates(self) -> list[Template]:
        result = await self.db.execute(select(Template).order_by(Template.name))
        return list(result.scalars().all())

    async def get_template(self, template_id: UUID) -> Template | None:
        result = await self.db.execute(select(Template).where(Template.id == template_id))
        return result.scalar_one_or_none()

    async def create_template(
        self,
        name: str,
        config: dict,
        description: str | None = None,
        created_by: UUID | None = None,
        is_builtin: bool = False,
    ) -> Template:
        template = Template(
            name=name,
            description=description,
            config=config,
            created_by=created_by,
            is_builtin=is_builtin,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template
