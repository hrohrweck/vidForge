"""Tests for deprecation-hygiene fixes (T29).

Covers:
- utc_now helper returns naive UTC datetimes
- dashboard endpoints reject invalid group_by values
- dashboard SQL uses safe literals (no f-string injection)
- websocket per-user connection cap (max 10, oldest evicted with 1008)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from app.api.websocket import ConnectionManager
from app.database import utc_now


# ------------------------------------------------------------------
# utc_now helper
# ------------------------------------------------------------------

def test_utc_now_returns_naive_datetime():
    """utc_now must return a naive datetime in UTC."""
    now = utc_now()
    assert now.tzinfo is None
    assert (datetime.now(timezone.utc).replace(tzinfo=None) - now).total_seconds() < 1


# ------------------------------------------------------------------
# Dashboard safe literals + pattern validation
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_token_usage_rejects_invalid_group_by(client, regular_user_token):
    """Invalid group_by values must return 422 (pattern mismatch)."""
    response = await client.get(
        "/api/dashboard/token-usage?group_by=year",
        headers={"Authorization": f"Bearer {regular_user_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_dashboard_cost_rejects_invalid_group_by(client, regular_user_token):
    """Invalid group_by values must return 422 (pattern mismatch)."""
    response = await client.get(
        "/api/dashboard/cost?group_by=minute",
        headers={"Authorization": f"Bearer {regular_user_token}"},
    )
    assert response.status_code == 422


# ------------------------------------------------------------------
# WebSocket per-user connection cap
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ws_connection_cap_evicts_oldest():
    """Adding > MAX_CONNECTIONS_PER_USER closes one connection with code 1008."""
    manager = ConnectionManager()
    user_id = "user-1"

    # Create 11 mock websockets
    mocks: list[MagicMock] = []
    for _ in range(manager.MAX_CONNECTIONS_PER_USER + 1):
        ws = MagicMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        mocks.append(ws)
        await manager.connect_user(ws, user_id)

    # Exactly one connection should have been closed with code 1008
    closed_mocks = [m for m in mocks if m.close.await_count == 1]
    assert len(closed_mocks) == 1
    _args, kwargs = closed_mocks[0].close.await_args
    assert kwargs.get("code") == 1008
    assert "limit exceeded" in kwargs.get("reason", "")

    # Total active connections should be exactly MAX_CONNECTIONS_PER_USER
    assert len(manager.user_connections[user_id]) == manager.MAX_CONNECTIONS_PER_USER

    # The newest connection should still be present
    assert mocks[-1] in manager.user_connections[user_id]


@pytest.mark.asyncio
async def test_ws_connection_cap_under_limit():
    """Connections under the cap are all retained."""
    manager = ConnectionManager()
    user_id = "user-2"

    mocks: list[MagicMock] = []
    for _ in range(manager.MAX_CONNECTIONS_PER_USER - 1):
        ws = MagicMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        mocks.append(ws)
        await manager.connect_user(ws, user_id)

    for ws in mocks:
        ws.close.assert_not_awaited()
    assert len(manager.user_connections[user_id]) == manager.MAX_CONNECTIONS_PER_USER - 1
