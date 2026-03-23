from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Permission,
    Group,
    UserGroup,
    GroupPermission,
    User,
    get_db,
)


async def has_permission(user: User, permission: str, db: AsyncSession) -> bool:
    """Check if user has a specific permission."""
    if user.is_superuser:
        return True

    result = await db.execute(
        select(Permission)
        .join(GroupPermission, GroupPermission.permission_id == Permission.id)
        .join(UserGroup, UserGroup.group_id == GroupPermission.group_id)
        .where(UserGroup.user_id == user.id)
        .where(Permission.name == permission)
    )
    return result.scalar_one_or_none() is not None


async def get_user_permissions(user: User, db: AsyncSession) -> list[str]:
    """Get all permission names for a user."""
    if user.is_superuser:
        result = await db.execute(select(Permission.name))
        return [row[0] for row in result.all()]

    result = await db.execute(
        select(Permission.name)
        .join(GroupPermission, GroupPermission.permission_id == Permission.id)
        .join(UserGroup, UserGroup.group_id == GroupPermission.group_id)
        .where(UserGroup.user_id == user.id)
    )
    return [row[0] for row in result.all()]


async def get_user_groups(user: User, db: AsyncSession) -> list[dict]:
    """Get all groups for a user with their IDs."""
    result = await db.execute(
        select(Group)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .where(UserGroup.user_id == user.id)
    )
    groups = result.scalars().all()
    return [{"id": str(g.id), "name": g.name, "description": g.description} for g in groups]


async def assign_user_to_group(user_id, group_name: str, db: AsyncSession) -> bool:
    """Assign a user to a group by name."""
    result = await db.execute(select(Group).where(Group.name == group_name))
    group = result.scalar_one_or_none()
    if not group:
        return False

    existing = await db.execute(
        select(UserGroup).where(
            UserGroup.user_id == user_id,
            UserGroup.group_id == group.id,
        )
    )
    if existing.scalar_one_or_none():
        return True

    user_group = UserGroup(user_id=user_id, group_id=group.id)
    db.add(user_group)
    return True


def require_permission(permission: str):
    """Dependency that requires a specific permission."""
    from app.api.auth import get_current_user

    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not await has_permission(user, permission, db):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{permission}' required",
            )
        return user

    return Depends(checker)


def require_any_permission(permissions: list[str]):
    """Dependency that requires any of the specified permissions."""
    from app.api.auth import get_current_user

    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        for perm in permissions:
            if await has_permission(user, perm, db):
                return user
        raise HTTPException(
            status_code=403,
            detail=f"One of permissions {permissions} required",
        )

    return Depends(checker)
