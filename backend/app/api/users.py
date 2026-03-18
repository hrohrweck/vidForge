from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.database import User, get_db

router = APIRouter()


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None


@router.get("/me", response_model=UserResponse)
async def get_user_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
