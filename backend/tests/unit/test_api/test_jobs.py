import pytest
from httpx import AsyncClient
from uuid import uuid4
import io
import re

from app.database import User, Job, Template


class TestJobsAPIAuthorization:
    """Authorization tests for jobs endpoints."""

    @pytest.mark.asyncio
    async def test_user_can_only_see_own_jobs(
        self,
        client: AsyncClient,
        regular_user_token: str,
        superuser_token: str,
        job_for_user: Job,
        db_session,
        regular_user,
        superuser,
        template,
    ):
        job_b = Job(
            id=uuid4(),
            user_id=superuser.id,
            template_id=template.id,
            status="pending",
            input_data={"prompt": "test"},
        )
        db_session.add(job_b)
        await db_session.commit()

        response = await client.get(
            "/api/jobs", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 200
        jobs = response.json()

        job_ids = [job["id"] for job in jobs]
        assert str(job_for_user.id) in job_ids
        assert str(job_b.id) not in job_ids

    @pytest.mark.asyncio
    async def test_user_can_only_delete_own_jobs(
        self, client: AsyncClient, regular_user_token: str, db_session, superuser, template
    ):
        job_b = Job(
            id=uuid4(),
            user_id=superuser.id,
            template_id=template.id,
            status="pending",
            input_data={"prompt": "test"},
        )
        db_session.add(job_b)
        await db_session.commit()

        response = await client.delete(
            f"/api/jobs/{job_b.id}", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_user_can_delete_own_job(
        self, client: AsyncClient, regular_user_token: str, job_for_user: Job
    ):
        response = await client.delete(
            f"/api/jobs/{job_for_user.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_create_jobs(self, client: AsyncClient):
        response = await client.post("/api/jobs", json={"template_id": str(uuid4())})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_batch_job_requires_authentication(self, client: AsyncClient):
        response = await client.post(
            "/api/jobs/batch", json={"template_id": str(uuid4()), "jobs": [{"prompt": "test"}]}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_csv_upload_requires_authentication(self, client: AsyncClient):
        csv_content = b"prompt\ntest1\ntest2"
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={uuid4()}",
            files={"file": ("test.csv", csv_file, "text/csv")},
        )
        assert response.status_code == 401


class TestJobsAPIValidation:
    """Input validation tests."""

    @pytest.mark.asyncio
    async def test_batch_job_validates_template_exists(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.post(
            "/api/jobs/batch",
            json={"template_id": str(uuid4()), "jobs": [{"prompt": "test"}]},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_csv_upload_rejects_non_csv_files(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        txt_content = b"This is not a CSV"
        txt_file = io.BytesIO(txt_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}",
            files={"file": ("test.txt", txt_file, "text/plain")},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_csv_upload_validates_headers(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        csv_content = b"wrong_header\ntest1"
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}&auto_start=false",
            files={"file": ("test.csv", csv_file, "text/csv")},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_csv_upload_rejects_empty_file(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        csv_content = b""
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}",
            files={"file": ("test.csv", csv_file, "text/csv")},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 400


class TestJobsAPIFunctionality:
    """Functional tests for jobs API."""

    @pytest.mark.asyncio
    async def test_create_single_job(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        response = await client.post(
            "/api/jobs",
            json={
                "template_id": str(template.id),
                "input_data": {"prompt": "test video"},
                "auto_start": False,
            },
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["input_data"]["prompt"] == "test video"

    @pytest.mark.asyncio
    async def test_create_batch_job_from_json(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        response = await client.post(
            "/api/jobs/batch",
            json={
                "template_id": str(template.id),
                "jobs": [{"prompt": "video 1"}, {"prompt": "video 2"}, {"prompt": "video 3"}],
                "auto_start": False,
            },
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created_count"] == 3
        assert len(data["job_ids"]) == 3

    @pytest.mark.asyncio
    async def test_create_batch_job_from_csv(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        csv_content = b"prompt\nvideo 1\nvideo 2\nvideo 3"
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}&auto_start=false",
            files={"file": ("test.csv", csv_file, "text/csv")},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created_count"] == 3
        assert len(data["job_ids"]) == 3

    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(
        self, client: AsyncClient, regular_user_token: str, job_for_user: Job, db_session
    ):
        job_for_user.status = "completed"
        await db_session.commit()

        response = await client.get(
            "/api/jobs?status=completed", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 200
        jobs = response.json()

        for job in jobs:
            assert job["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_specific_job(
        self, client: AsyncClient, regular_user_token: str, job_for_user: Job
    ):
        response = await client.get(
            f"/api/jobs/{job_for_user.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(job_for_user.id)

    @pytest.mark.asyncio
    async def test_create_job_with_provider_preference(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        response = await client.post(
            "/api/jobs",
            json={
                "template_id": str(template.id),
                "input_data": {"prompt": "provider local test"},
                "auto_start": False,
                "provider_preference": "local",
            },
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["provider_preference"] == "local"
        assert data["estimated_cost"] is None
        assert data["actual_cost"] is None

    @pytest.mark.asyncio
    async def test_invalid_provider_preference_defaults_to_auto(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        response = await client.post(
            "/api/jobs",
            json={
                "template_id": str(template.id),
                "input_data": {"prompt": "invalid preference"},
                "auto_start": False,
                "provider_preference": "gpu",
            },
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider_preference"] == "auto"

    @pytest.mark.asyncio
    async def test_batch_jobs_with_provider_preference(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        response = await client.post(
            "/api/jobs/batch",
            json={
                "template_id": str(template.id),
                "jobs": [{"prompt": "batch 1"}, {"prompt": "batch 2"}],
                "auto_start": False,
                "provider_preference": "runpod",
            },
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["created_count"] == 2
        assert len(data["job_ids"]) == 2
        for job_id in data["job_ids"]:
            assert re.fullmatch(r"[0-9a-fA-F-]{36}", job_id)

    @pytest.mark.asyncio
    async def test_batch_csv_with_provider_preference(
        self, client: AsyncClient, regular_user_token: str, template: Template
    ):
        csv_content = b"prompt\nbatch csv 1\nbatch csv 2"
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}&auto_start=false&provider_preference=runpod",
            files={"file": ("test.csv", csv_file, "text/csv")},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["created_count"] == 2
        assert all(re.fullmatch(r"[0-9a-fA-F-]{36}", job_id) for job_id in data["job_ids"])

    @pytest.mark.asyncio
    async def test_start_job_uses_stored_preference(
        self,
        client: AsyncClient,
        regular_user_token: str,
        job_for_user: Job,
        db_session,
        monkeypatch,
    ):
        class FakeTask:
            calls = []

            def delay(self, *args, **kwargs):
                self.calls.append((args, kwargs))

        fake_task = FakeTask()
        import app.api.jobs as jobs_api

        monkeypatch.setattr(jobs_api, "process_video_job", fake_task)

        job_for_user.provider_preference = "runpod"
        await db_session.commit()

        response = await client.post(
            f"/api/jobs/{job_for_user.id}/start",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )

        assert response.status_code == 200
        assert fake_task.calls
        assert fake_task.calls[0][1]["provider_preference"] == "runpod"

    @pytest.mark.asyncio
    async def test_retry_job_clears_cost_and_enqueues_with_preference(
        self,
        client: AsyncClient,
        regular_user_token: str,
        job_for_user: Job,
        db_session,
        monkeypatch,
    ):
        class FakeTask:
            calls = []

            def delay(self, *args, **kwargs):
                self.calls.append((args, kwargs))

        fake_task = FakeTask()
        import app.api.jobs as jobs_api

        monkeypatch.setattr(jobs_api, "process_video_job", fake_task)

        job_for_user.status = "failed"
        job_for_user.actual_cost = 7
        job_for_user.provider_preference = "local"
        await db_session.commit()

        response = await client.post(
            f"/api/jobs/{job_for_user.id}/retry",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["actual_cost"] is None
        assert body["status"] == "pending"
        assert body["provider_preference"] == "local"
        assert fake_task.calls
        assert fake_task.calls[0][1]["provider_preference"] == "local"

    @pytest.mark.asyncio
    async def test_cannot_access_other_user_job(
        self, client: AsyncClient, regular_user_token: str, db_session, superuser, template
    ):
        job_b = Job(
            id=uuid4(),
            user_id=superuser.id,
            template_id=template.id,
            status="pending",
            input_data={"prompt": "test"},
        )
        db_session.add(job_b)
        await db_session.commit()

        response = await client.get(
            f"/api/jobs/{job_b.id}", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 404
