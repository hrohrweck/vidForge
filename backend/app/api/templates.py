from datetime import datetime
from typing import Any
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi import UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import Template, User, get_db

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    config: dict[str, Any]


class TemplateResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    config: dict[str, Any]
    is_builtin: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Template]:
    result = await db.execute(select(Template).order_by(Template.name))
    return list(result.scalars().all())


@router.post("", response_model=TemplateResponse)
async def create_template(
    template_data: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Template:
    template = Template(
        name=template_data.name,
        description=template_data.description,
        config=template_data.config,
        created_by=current_user.id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Template:
    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    template_data: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Template:
    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot modify built-in templates")

    if template.created_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this template"
        )

    template.name = template_data.name
    template.description = template_data.description
    template.config = template_data.config
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}")
async def delete_template(
    template_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot delete built-in templates")

    if template.created_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this template"
        )

    await db.delete(template)
    await db.commit()
    return {"status": "deleted"}
