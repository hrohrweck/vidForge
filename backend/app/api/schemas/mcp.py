from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MCPServerCreate(BaseModel):
    name: str
    description: str | None = None
    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None


class MCPServerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    is_active: bool | None = None


class MCPServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    command: str
    args: list[str] | None
    env_keys: list[str] | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MCPServerWithCredentials(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    command: str
    args: list[str] | None
    env: dict[str, str] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime