"""Integration tests for job creation and listing.

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/ -v
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_create_and_list_job(authenticated_client):
    """Test creating a job and listing it."""
    # Create a template first (or use seeded ones)
    response = await authenticated_client.get("/api/templates")
    assert response.status_code == 200
    templates = response.json()

    if not templates:
        pytest.skip("No templates available (seeding may have failed)")

    template_id = templates[0]["id"]

    # Create a job
    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {"prompt": "integration test job"},
            "auto_start": False,
        },
    )
    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "pending"
    assert job["input_data"]["prompt"] == "integration test job"

    # List jobs
    response = await authenticated_client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) >= 1
    assert any(j["id"] == job["id"] for j in jobs)

    # Get specific job
    response = await authenticated_client.get(f"/api/jobs/{job['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == job["id"]


@pytest.mark.asyncio
async def test_batch_job_creation(authenticated_client):
    """Test creating multiple jobs at once."""
    response = await authenticated_client.get("/api/templates")
    templates = response.json()
    if not templates:
        pytest.skip("No templates available")
    template_id = templates[0]["id"]

    response = await authenticated_client.post(
        "/api/jobs/batch",
        json={
            "template_id": template_id,
            "jobs": [
                {"prompt": "batch job 1"},
                {"prompt": "batch job 2"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created_count"] == 2
    assert len(data["job_ids"]) == 2


@pytest.mark.asyncio
async def test_delete_job(authenticated_client):
    """Test deleting a job."""
    response = await authenticated_client.get("/api/templates")
    templates = response.json()
    if not templates:
        pytest.skip("No templates available")
    template_id = templates[0]["id"]

    # Create a job
    response = await authenticated_client.post(
        "/api/jobs",
        json={
            "template_id": template_id,
            "input_data": {"prompt": "to be deleted"},
            "auto_start": False,
        },
    )
    job_id = response.json()["id"]

    # Delete it
    response = await authenticated_client.delete(f"/api/jobs/{job_id}")
    assert response.status_code == 200

    # Verify it's gone
    response = await authenticated_client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 404
