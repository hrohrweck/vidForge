from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import Style, User, get_db

router = APIRouter()


class StyleCreate(BaseModel):
    name: str
    category: str | None = None
    params: dict[str, Any] = {}


class StyleResponse(BaseModel):
    id: UUID
    name: str
    category: str | None
    params: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[StyleResponse])
async def list_styles(
    category: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Style]:
    query = select(Style).order_by(Style.name)
    if category:
        query = query.where(Style.category == category)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=StyleResponse)
async def create_style(
    style_data: StyleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Style:
    result = await db.execute(select(Style).where(Style.name == style_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="Style with this name already exists"
        )

    style = Style(
        name=style_data.name,
        category=style_data.category,
        params=style_data.params,
    )
    db.add(style)
    await db.commit()
    await db.refresh(style)
    return style


@router.get("/{style_id}", response_model=StyleResponse)
async def get_style(
    style_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Style:
    result = await db.execute(select(Style).where(Style.id == style_id))
    style = result.scalar_one_or_none()
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")
    return style


@router.put("/{style_id}", response_model=StyleResponse)
async def update_style(
    style_id: UUID,
    style_data: StyleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Style:
    result = await db.execute(select(Style).where(Style.id == style_id))
    style = result.scalar_one_or_none()
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    style.name = style_data.name
    style.category = style_data.category
    style.params = style_data.params
    await db.commit()
    await db.refresh(style)
    return style


@router.delete("/{style_id}")
async def delete_style(
    style_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Style).where(Style.id == style_id))
    style = result.scalar_one_or_none()
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    await db.delete(style)
    await db.commit()
    return {"status": "deleted"}
