"""WebSocket authentication helper.

Validates JWT tokens from WebSocket query parameters and returns the
authenticated user. JWT in query string is the standard for browser
WebSocket auth (browsers cannot set custom headers on the WS handshake).

This helper does NOT call ``websocket.accept()`` — callers must accept the
connection only after a successful auth to reject unauthenticated clients
with close code 1008 (policy violation).
"""

from uuid import UUID

from fastapi import WebSocket
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import TOKEN_COOKIE_NAME
from app.config import get_settings
from app.database import User, get_db

settings = get_settings()


async def authenticate_websocket(
    websocket: WebSocket,
    token: str | None = None,
    db: AsyncSession | None = None,
) -> User | None:
    """Authenticate a WebSocket connection via JWT in the query string.

    Args:
        websocket: The FastAPI WebSocket connection (used to read the
            ``token`` query parameter if ``token`` is not provided).
        token: Optional pre-extracted JWT. If ``None``, the helper reads
            ``websocket.query_params.get("token")``.
        db: Optional database session. If ``None``, one is created via
            the ``get_db`` generator and closed before returning.

    Returns:
        The authenticated ``User`` on success, or ``None`` if the token is
        missing, malformed, expired, invalid, or the user no longer exists.
        Never raises — all failure modes return ``None`` so the caller can
        close the WebSocket uniformly.
    """
    if token is None:
        token = websocket.query_params.get("token")

    if not token:
        token = websocket.cookies.get(TOKEN_COOKIE_NAME)

    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    except Exception:
        return None

    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        return None

    if db is not None:
        return await _lookup_user(db, user_uuid)

    async for session in get_db():
        return await _lookup_user(session, user_uuid)

    return None


async def _lookup_user(db: AsyncSession, user_uuid: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_uuid))
    return result.scalar_one_or_none()
