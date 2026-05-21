"""Integration tests for authentication flow.

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/ -v
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_register_and_login(authenticated_client):
    """Test full register -> login -> access protected endpoint flow."""
    response = await authenticated_client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "integration@test.com"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_token_refresh(authenticated_client):
    """Test token refresh endpoint."""
    response = await authenticated_client.post("/api/auth/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_protected_endpoint_without_auth(integration_client):
    """Test that protected endpoints reject unauthenticated requests."""
    response = await integration_client.get("/api/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_login_with_wrong_password(integration_client):
    """Test login failure with wrong password."""
    # Register first
    await integration_client.post(
        "/api/auth/register",
        json={"email": "wrong@test.com", "password": "correctpass"},
    )
    # Try login with wrong password
    response = await integration_client.post(
        "/api/auth/login",
        json={"email": "wrong@test.com", "password": "wrongpass"},
    )
    assert response.status_code == 401
