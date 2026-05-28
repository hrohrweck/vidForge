"""Integration tests for job-avatar assignment validation.

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/test_job_avatar_integration.py -v
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _create_avatar(client: AsyncClient, name: str, gender: str = "Female") -> dict:
    resp = await client.post(
        "/api/avatars",
        json={"name": name, "gender": gender},
    )
    assert resp.status_code == 201, f"Avatar creation failed: {resp.text}"
    return resp.json()


async def _get_template_id(client: AsyncClient) -> str:
    resp = await client.get("/api/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert templates, "No templates available — seeding may have failed"
    return templates[0]["id"]


async def _register_and_login(client: AsyncClient, email: str, password: str) -> str:
    """Register a new user, login, and return the access token."""
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    return login_resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Test 1: valid avatar assignment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_create_with_valid_avatar(authenticated_client: AsyncClient):
    template_id = await _get_template_id(authenticated_client)
    avatar = await _create_avatar(authenticated_client, "Eva")

    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {
                "prompt": "a test scene",
                "avatars": [
                    {"avatar_id": avatar["id"], "role": "lead actor"},
                ],
            },
            "auto_start": False,
        },
    )

    assert response.status_code == 200, f"Job creation failed: {response.text}"
    job = response.json()
    assert job["status"] == "pending"
    assert job["avatars"] is not None, "avatars field missing from response"
    assert len(job["avatars"]) == 1
    assert job["avatars"][0]["avatar_id"] == avatar["id"]
    assert job["avatars"][0]["avatar_name"] == "Eva"
    assert job["avatars"][0]["role"] == "lead actor"


# ---------------------------------------------------------------------------
# Test 2: invalid avatar UUID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_create_with_invalid_avatar_id(authenticated_client: AsyncClient):
    template_id = await _get_template_id(authenticated_client)

    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {
                "prompt": "test",
                "avatars": [
                    {"avatar_id": "not-a-valid-uuid", "role": "narrator"},
                ],
            },
            "auto_start": False,
        },
    )

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    detail = response.json()["detail"]
    assert "errors" in detail
    assert any("invalid UUID" in e for e in detail["errors"])


# ---------------------------------------------------------------------------
# Test 3: soft-deleted avatar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_create_with_soft_deleted_avatar(authenticated_client: AsyncClient):
    template_id = await _get_template_id(authenticated_client)
    avatar = await _create_avatar(authenticated_client, "Ghost")

    del_resp = await authenticated_client.delete(f"/api/avatars/{avatar['id']}")
    assert del_resp.status_code == 204

    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {
                "prompt": "test",
                "avatars": [
                    {"avatar_id": avatar["id"], "role": "should fail"},
                ],
            },
            "auto_start": False,
        },
    )

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    detail = response.json()["detail"]
    assert "errors" in detail
    assert any(
        "not found" in e.lower() or "access denied" in e.lower()
        for e in detail["errors"]
    )


# ---------------------------------------------------------------------------
# Test 4: another user's avatar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_create_with_another_users_avatar(authenticated_client: AsyncClient):
    template_id = await _get_template_id(authenticated_client)

    # Remember user1's token, then register a second user via the API
    user1_token = authenticated_client.headers.get("Authorization", "")

    del authenticated_client.headers["Authorization"]
    user2_token = await _register_and_login(
        authenticated_client, "other@example.com", "otherpass123"
    )

    authenticated_client.headers["Authorization"] = f"Bearer {user2_token}"
    other_avatar = await _create_avatar(authenticated_client, "Stranger")

    # Restore user1 and attempt to use user2's avatar
    authenticated_client.headers["Authorization"] = user1_token

    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {
                "prompt": "test",
                "avatars": [
                    {"avatar_id": other_avatar["id"], "role": "intruder"},
                ],
            },
            "auto_start": False,
        },
    )

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    detail = response.json()["detail"]
    assert "errors" in detail
    assert any(
        "not found" in e.lower() or "access denied" in e.lower()
        for e in detail["errors"]
    )


# ---------------------------------------------------------------------------
# Test 5: no avatars (backward compat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_create_without_avatars(authenticated_client: AsyncClient):
    template_id = await _get_template_id(authenticated_client)

    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {"prompt": "no avatar job"},
            "auto_start": False,
        },
    )

    assert response.status_code == 200, f"Job creation failed: {response.text}"
    job = response.json()
    assert job["status"] == "pending"
    avatars = job.get("avatars")
    assert avatars is None or avatars == [], f"Unexpected avatars value: {avatars}"


# ---------------------------------------------------------------------------
# Test 6: GET /api/jobs/{id} includes avatars
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_response_includes_avatar_assignments(authenticated_client: AsyncClient):
    template_id = await _get_template_id(authenticated_client)
    avatar = await _create_avatar(authenticated_client, "Alice")

    create_resp = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {
                "prompt": "scene with Alice",
                "avatars": [
                    {
                        "avatar_id": avatar["id"],
                        "role": "protagonist",
                        "consistency_strategy_override": "face_swap",
                    },
                ],
            },
            "auto_start": False,
        },
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["id"]

    get_resp = await authenticated_client.get(f"/api/jobs/{job_id}")
    assert get_resp.status_code == 200
    job = get_resp.json()

    assert job["avatars"] is not None, "avatars field missing from GET response"
    assert len(job["avatars"]) == 1
    a = job["avatars"][0]
    assert a["avatar_id"] == avatar["id"]
    assert a["avatar_name"] == "Alice"
    assert a["role"] == "protagonist"
    assert a["consistency_strategy_override"] == "face_swap"


# ---------------------------------------------------------------------------
# Test 7: duplicate avatar assignment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_avatar_assignment(authenticated_client: AsyncClient):
    template_id = await _get_template_id(authenticated_client)
    avatar = await _create_avatar(authenticated_client, "Dupe")

    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {
                "prompt": "duplicate avatar test",
                "avatars": [
                    {"avatar_id": avatar["id"], "role": "first"},
                    {"avatar_id": avatar["id"], "role": "second (duplicate)"},
                ],
            },
            "auto_start": False,
        },
    )

    assert response.status_code == 200, f"Unexpected status {response.status_code}: {response.text}"
    avatars = response.json().get("avatars", [])
    assert len(avatars) == 1, f"Duplicate avatar was not deduplicated: {avatars}"
