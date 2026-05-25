"""Admin endpoints for managing MCP servers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.chatbot.crypto import encrypt_credentials
from app.chatbot.mcp_client import MCPClientManager
from app.database import MCPServer, User, get_db

router = APIRouter()


class MCPServerAdminCreate(BaseModel):
    slug: str
    name: str
    url: str
    auth_type: str = "none"
    credentials: str | None = None


class MCPServerAdminUpdate(BaseModel):
    slug: str | None = None
    name: str | None = None
    url: str | None = None
    auth_type: str | None = None
    credentials: str | None = None
    enabled: bool | None = None


class MCPServerAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    url: str
    auth_type: str
    enabled: bool
    created_at: Any
    updated_at: Any


class MCPServerTestResult(BaseModel):
    ok: bool
    tools_count: int
    error: str | None = None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/mcp-servers", response_model=list[MCPServerAdminOut])
async def list_mcp_servers(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> list[MCPServer]:
    result = await db.execute(select(MCPServer).order_by(MCPServer.created_at.desc()))
    return list(result.scalars().all())


@router.post("/mcp-servers", response_model=MCPServerAdminOut, status_code=201)
async def create_mcp_server(
    payload: MCPServerAdminCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> MCPServer:
    existing = await db.execute(select(MCPServer).where(MCPServer.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="MCP server with this slug already exists")

    encrypted_creds: bytes | None = None
    if payload.credentials is not None:
        encrypted_creds = encrypt_credentials(payload.credentials)

    server = MCPServer(
        slug=payload.slug,
        name=payload.name,
        url=payload.url,
        auth_type=payload.auth_type,
        encrypted_credentials=encrypted_creds,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


@router.patch("/mcp-servers/{server_id}", response_model=MCPServerAdminOut)
async def update_mcp_server(
    server_id: UUID,
    payload: MCPServerAdminUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> MCPServer:
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    if payload.slug is not None:
        existing = await db.execute(
            select(MCPServer).where(MCPServer.slug == payload.slug, MCPServer.id != server_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="MCP server with this slug already exists")
        server.slug = payload.slug

    if payload.name is not None:
        server.name = payload.name
    if payload.url is not None:
        server.url = payload.url
    if payload.auth_type is not None:
        server.auth_type = payload.auth_type
    if payload.enabled is not None:
        server.enabled = payload.enabled
    if payload.credentials is not None:
        server.encrypted_credentials = encrypt_credentials(payload.credentials)

    await db.commit()
    await db.refresh(server)
    return server


@router.delete("/mcp-servers/{server_id}")
async def delete_mcp_server(
    server_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, str]:
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    await db.execute(sql_delete(MCPServer).where(MCPServer.id == server_id))
    await db.commit()
    return {"status": "deleted", "server_id": str(server_id)}


@router.post("/mcp-servers/{server_id}/test", response_model=MCPServerTestResult)
async def test_mcp_server(
    server_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    manager = MCPClientManager(session_ttl_seconds=10, tool_cache_ttl_seconds=0)
    try:
        ok = await manager.health_check(server)  # type: ignore[arg-type]
        if not ok:
            return {"ok": False, "tools_count": 0, "error": "MCP server health check failed"}

        tools = await manager.list_tools(server.slug)
        return {"ok": True, "tools_count": len(tools), "error": None}
    except Exception as exc:
        return {"ok": False, "tools_count": 0, "error": str(exc)}
    finally:
        await manager.close()
