import pytest
from httpx import AsyncClient

from app.database import User, Job


class TestAdminAuthorization:
    """Critical authorization tests for admin endpoints."""

    @pytest.mark.asyncio
    async def test_non_superuser_cannot_access_admin_endpoints(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_user_cannot_access_admin(self, client: AsyncClient):
        response = await client.get("/api/admin/users")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_superuser_can_list_all_users(
        self, client: AsyncClient, superuser_token: str, regular_user: User
    ):
        response = await client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {superuser_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_superuser_can_view_dashboard(self, client: AsyncClient, superuser_token: str):
        response = await client.get(
            "/api/admin/dashboard", headers={"Authorization": f"Bearer {superuser_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data
        assert "recent_jobs" in data
        assert "total_users" in data["stats"]
        assert "total_jobs" in data["stats"]

    @pytest.mark.asyncio
    async def test_regular_user_cannot_view_dashboard(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/admin/dashboard", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_superuser_can_list_all_jobs(
        self, client: AsyncClient, superuser_token: str, job_for_user: Job
    ):
        response = await client.get(
            "/api/admin/jobs", headers={"Authorization": f"Bearer {superuser_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_regular_user_cannot_list_all_jobs(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/admin/jobs", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_superuser_can_cancel_job(
        self,
        client: AsyncClient,
        superuser_token: str,
        job_for_user: Job,
    ):
        response = await client.post(
            f"/api/admin/jobs/{job_for_user.id}/cancel",
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_regular_user_cannot_use_admin_job_endpoints(
        self, client: AsyncClient, regular_user_token: str, job_for_user: Job
    ):
        response = await client.post(
            f"/api/admin/jobs/{job_for_user.id}/cancel",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_endpoint_requires_authentication(self, client: AsyncClient):
        endpoints = [
            "/api/admin/users",
            "/api/admin/dashboard",
            "/api/admin/jobs",
        ]

        for endpoint in endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 401, f"Endpoint {endpoint} should require authentication"
