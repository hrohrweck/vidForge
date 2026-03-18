import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4
import io

from app.main import app
from app.database import Base, get_db, User, Job, Template
from app.api.auth import create_access_token

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def user_a(db_session: AsyncSession):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    user = User(
        id=uuid4(),
        email="user_a@example.com",
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def user_b(db_session: AsyncSession):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    user = User(
        id=uuid4(),
        email="user_b@example.com",
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def user_a_token(user_a):
    return create_access_token(data={"sub": user_a.email, "user_id": str(user_a.id)})


@pytest.fixture
def user_b_token(user_b):
    return create_access_token(data={"sub": user_b.email, "user_id": str(user_b.id)})


@pytest.fixture
async def template(db_session: AsyncSession):
    template = Template(
        id=uuid4(),
        name="Test Template",
        description="A test template",
        config={"inputs": [{"name": "prompt", "type": "text", "required": True}]},
        is_builtin=True,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def job_for_user_a(db_session: AsyncSession, user_a: User, template: Template):
    job = Job(
        id=uuid4(),
        user_id=user_a.id,
        template_id=template.id,
        status="pending",
        input_data={"prompt": "test"},
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.fixture
async def job_for_user_b(db_session: AsyncSession, user_b: User, template: Template):
    job = Job(
        id=uuid4(),
        user_id=user_b.id,
        template_id=template.id,
        status="pending",
        input_data={"prompt": "test"},
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


class TestJobsAPIAuthorization:
    """Authorization tests for jobs endpoints."""

    @pytest.mark.asyncio
    async def test_user_can_only_see_own_jobs(
        self,
        client: AsyncClient,
        user_a_token: str,
        user_b_token: str,
        job_for_user_a: Job,
        job_for_user_b: Job,
    ):
        response = await client.get(
            "/api/jobs", headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response.status_code == 200
        jobs = response.json()

        job_ids = [job["id"] for job in jobs]
        assert str(job_for_user_a.id) in job_ids
        assert str(job_for_user_b.id) not in job_ids

    @pytest.mark.asyncio
    async def test_user_can_only_delete_own_jobs(
        self, client: AsyncClient, user_a_token: str, job_for_user_b: Job
    ):
        response = await client.delete(
            f"/api/jobs/{job_for_user_b.id}", headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_user_can_delete_own_job(
        self, client: AsyncClient, user_a_token: str, job_for_user_a: Job
    ):
        response = await client.delete(
            f"/api/jobs/{job_for_user_a.id}", headers={"Authorization": f"Bearer {user_a_token}"}
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
        self, client: AsyncClient, user_a_token: str
    ):
        response = await client.post(
            "/api/jobs/batch",
            json={"template_id": str(uuid4()), "jobs": [{"prompt": "test"}]},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_csv_upload_rejects_non_csv_files(
        self, client: AsyncClient, user_a_token: str, template: Template
    ):
        txt_content = b"This is not a CSV"
        txt_file = io.BytesIO(txt_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}",
            files={"file": ("test.txt", txt_file, "text/plain")},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_csv_upload_validates_headers(
        self, client: AsyncClient, user_a_token: str, template: Template
    ):
        csv_content = b"wrong_header\ntest1"
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}",
            files={"file": ("test.csv", csv_file, "text/csv")},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_csv_upload_rejects_empty_file(
        self, client: AsyncClient, user_a_token: str, template: Template
    ):
        csv_content = b""
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}",
            files={"file": ("test.csv", csv_file, "text/csv")},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 400


class TestJobsAPIFunctionality:
    """Functional tests for jobs API."""

    @pytest.mark.asyncio
    async def test_create_single_job(
        self, client: AsyncClient, user_a_token: str, template: Template
    ):
        response = await client.post(
            "/api/jobs",
            json={"template_id": str(template.id), "input_data": {"prompt": "test video"}},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["input_data"]["prompt"] == "test video"

    @pytest.mark.asyncio
    async def test_create_batch_job_from_json(
        self, client: AsyncClient, user_a_token: str, template: Template
    ):
        response = await client.post(
            "/api/jobs/batch",
            json={
                "template_id": str(template.id),
                "jobs": [{"prompt": "video 1"}, {"prompt": "video 2"}, {"prompt": "video 3"}],
                "auto_start": False,
            },
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created_count"] == 3
        assert len(data["job_ids"]) == 3

    @pytest.mark.asyncio
    async def test_create_batch_job_from_csv(
        self, client: AsyncClient, user_a_token: str, template: Template
    ):
        csv_content = b"prompt\nvideo 1\nvideo 2\nvideo 3"
        csv_file = io.BytesIO(csv_content)

        response = await client.post(
            f"/api/jobs/batch/csv?template_id={template.id}&auto_start=false",
            files={"file": ("test.csv", csv_file, "text/csv")},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created_count"] == 3
        assert len(data["job_ids"]) == 3

    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(
        self, client: AsyncClient, user_a_token: str, job_for_user_a: Job, db_session: AsyncSession
    ):
        job_for_user_a.status = "completed"
        await db_session.commit()

        response = await client.get(
            "/api/jobs?status=completed", headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response.status_code == 200
        jobs = response.json()

        for job in jobs:
            assert job["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_specific_job(
        self, client: AsyncClient, user_a_token: str, job_for_user_a: Job
    ):
        response = await client.get(
            f"/api/jobs/{job_for_user_a.id}", headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(job_for_user_a.id)

    @pytest.mark.asyncio
    async def test_cannot_access_other_user_job(
        self, client: AsyncClient, user_a_token: str, job_for_user_b: Job
    ):
        response = await client.get(
            f"/api/jobs/{job_for_user_b.id}", headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response.status_code == 404
