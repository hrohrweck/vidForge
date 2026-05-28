"""Tests for dashboard endpoints: GET /api/dashboard/token-usage and /api/dashboard/cost.

These endpoints use PostgreSQL-specific ``date_trunc`` via raw SQL, so the DB
session is mocked with MagicMock rows rather than hitting the SQLite test DB.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.database import get_db
from app.main import app


# ── helpers ────────────────────────────────────────────────────────────────


def _make_token_bucket(bucket: datetime, model_id: str, prompt_tokens: int,
                       completion_tokens: int, total_tokens: int) -> MagicMock:
    """Return a MagicMock row matching the token‑usage query columns."""
    row = MagicMock()
    row.bucket = bucket
    row.model_id = model_id
    row.prompt_tokens = prompt_tokens
    row.completion_tokens = completion_tokens
    row.total_tokens = total_tokens
    return row


def _make_cost_bucket(bucket: datetime, model_id: str, cost: float) -> MagicMock:
    """Return a MagicMock row matching the cost query columns."""
    row = MagicMock()
    row.bucket = bucket
    row.model_id = model_id
    row.cost = cost
    return row


def _install_mock_db(regular_user, rows: list[MagicMock]) -> AsyncMock:
    """Override ``get_db`` with a mock session that:

    * returns *regular_user* from ``scalar_one_or_none()`` (used by
      ``get_current_user``), and
    * returns *rows* from ``fetchall()`` (used by every dashboard query).

    Call ``_uninstall_mock_db()`` to restore the original override.
    """
    global _original_get_db_override
    _original_get_db_override = app.dependency_overrides.get(get_db)

    mock_db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = regular_user
    result_mock.fetchall.return_value = rows
    mock_db.execute = AsyncMock(return_value=result_mock)

    app.dependency_overrides[get_db] = lambda: mock_db
    return mock_db


def _uninstall_mock_db() -> None:
    """Restore the real ``get_db`` override (SQLite session)."""
    if _original_get_db_override is not None:
        app.dependency_overrides[get_db] = _original_get_db_override
    elif get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]


_original_get_db_override = None


# ── auth ───────────────────────────────────────────────────────────────────


class TestDashboardAuth:
    """Both dashboard endpoints reject unauthenticated requests."""

    @pytest.mark.asyncio
    async def test_token_usage_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/dashboard/token-usage")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cost_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/dashboard/cost")
        assert response.status_code == 401


# ── token‑usage ────────────────────────────────────────────────────────────


class TestTokenUsage:
    """Tests for ``GET /api/dashboard/token-usage``."""

    @pytest.mark.asyncio
    async def test_returns_buckets_with_default_params(
        self, client: AsyncClient, regular_user_token: str, regular_user,
    ):
        """With no query params the endpoint uses a 30‑day window and
        day-level grouping by default."""
        rows = [
            _make_token_bucket(
                bucket=datetime(2026, 5, 15, 12, 0, 0),
                model_id="qwen3.6",
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
            ),
            _make_token_bucket(
                bucket=datetime(2026, 5, 16, 8, 0, 0),
                model_id="llama3.3",
                prompt_tokens=200,
                completion_tokens=40,
                total_tokens=240,
            ),
        ]
        _install_mock_db(regular_user, rows)

        try:
            response = await client.get(
                "/api/dashboard/token-usage",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "buckets" in data
            assert len(data["buckets"]) == 2
            assert data["buckets"][0]["model_id"] == "qwen3.6"
            assert data["buckets"][0]["prompt_tokens"] == 100
            assert data["buckets"][0]["completion_tokens"] == 20
            assert data["buckets"][0]["total_tokens"] == 120
            assert data["buckets"][1]["model_id"] == "llama3.3"
            assert data["buckets"][1]["total_tokens"] == 240
        finally:
            _uninstall_mock_db()

    @pytest.mark.asyncio
    async def test_respects_group_by_month(
        self, client: AsyncClient, regular_user_token: str, regular_user,
    ):
        """``?group_by=month`` produces one bucket per month (the endpoint
        forwards the value into ``date_trunc``)."""
        rows = [
            _make_token_bucket(
                bucket=datetime(2026, 1, 1, 0, 0, 0),
                model_id="qwen3.6",
                prompt_tokens=500,
                completion_tokens=100,
                total_tokens=600,
            ),
            _make_token_bucket(
                bucket=datetime(2026, 2, 1, 0, 0, 0),
                model_id="qwen3.6",
                prompt_tokens=300,
                completion_tokens=50,
                total_tokens=350,
            ),
            _make_token_bucket(
                bucket=datetime(2026, 3, 1, 0, 0, 0),
                model_id="qwen3.6",
                prompt_tokens=700,
                completion_tokens=150,
                total_tokens=850,
            ),
        ]
        _install_mock_db(regular_user, rows)

        try:
            response = await client.get(
                "/api/dashboard/token-usage",
                params={"group_by": "month"},
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["buckets"]) == 3
            # All rows share the same model, so three months → three buckets.
            for b in data["buckets"]:
                assert b["model_id"] == "qwen3.6"
        finally:
            _uninstall_mock_db()

    @pytest.mark.asyncio
    async def test_rejects_invalid_group_by(
        self, client: AsyncClient, regular_user_token: str,
    ):
        """``?group_by=invalid`` must return 422 (FastAPI query‑param
        validation).  No DB call needed."""
        response = await client.get(
            "/api/dashboard/token-usage",
            params={"group_by": "invalid"},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 422


# ── cost ───────────────────────────────────────────────────────────────────


class TestCost:
    """Tests for ``GET /api/dashboard/cost``."""

    @pytest.mark.asyncio
    async def test_returns_buckets_with_default_params(
        self, client: AsyncClient, regular_user_token: str, regular_user,
    ):
        """The cost endpoint aggregates ``jobs`` data into timestamped
        buckets."""
        rows = [
            _make_cost_bucket(
                bucket=datetime(2026, 5, 20, 14, 0, 0),
                model_id="script_to_video",
                cost=1.25,
            ),
            _make_cost_bucket(
                bucket=datetime(2026, 5, 21, 9, 0, 0),
                model_id="prompt_to_video",
                cost=0.75,
            ),
        ]
        _install_mock_db(regular_user, rows)

        try:
            response = await client.get(
                "/api/dashboard/cost",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "buckets" in data
            assert len(data["buckets"]) == 2
            assert data["buckets"][0]["model_id"] == "script_to_video"
            assert data["buckets"][0]["cost"] == 1.25
            assert data["buckets"][1]["model_id"] == "prompt_to_video"
            assert data["buckets"][1]["cost"] == 0.75
        finally:
            _uninstall_mock_db()

    @pytest.mark.asyncio
    async def test_handles_empty_data_gracefully(
        self, client: AsyncClient, regular_user_token: str, regular_user,
    ):
        """When there are no matching jobs the response is ``{"buckets": []}``."""
        _install_mock_db(regular_user, [])

        try:
            response = await client.get(
                "/api/dashboard/cost",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data == {"buckets": []}
        finally:
            _uninstall_mock_db()
