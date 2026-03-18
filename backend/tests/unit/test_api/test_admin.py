import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4

from app.main import app
from app.database import Base, get_db, User
from app.api.auth import get_current_user, create_access_token

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
async def regular_user(db_session: AsyncSession):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    user = User(
        id=uuid4(),
        email="regular@example.com",
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def superuser(db_session: AsyncSession):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    user = User(
        id=uuid4(),
        email="admin@example.com",
        hashed_password=pwd_context.hash("admin123"),
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def regular_user_token(regular_user):
    return create_access_token(data={"sub": regular_user.email, "user_id": str(regular_user.id)})


@pytest.fixture
def superuser_token(superuser):
    return create_access_token(data={"sub": superuser.email, "user_id": str(superuser.id)})


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
    async def test_superuser_can_view_system_stats(self, client: AsyncClient, superuser_token: str):
        response = await client.get(
            "/api/admin/stats", headers={"Authorization": f"Bearer {superuser_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "total_jobs" in data
        assert "active_jobs" in data

    @pytest.mark.asyncio
    async def test_regular_user_cannot_view_system_stats(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/admin/stats", headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_superuser_can_toggle_user_status(
        self,
        client: AsyncClient,
        superuser_token: str,
        regular_user: User,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/api/admin/users/{regular_user.id}/toggle-active",
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

        await db_session.refresh(regular_user)
        assert regular_user.is_active == False

    @pytest.mark.asyncio
    async def test_regular_user_cannot_toggle_user_status(
        self, client: AsyncClient, regular_user_token: str, superuser: User
    ):
        response = await client.post(
            f"/api/admin/users/{superuser.id}/toggle-active",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_superuser_cannot_deactivate_themselves(
        self, client: AsyncClient, superuser: User, superuser_token: str
    ):
        response = await client.post(
            f"/api/admin/users/{superuser.id}/toggle-active",
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_endpoint_requires_authentication(self, client: AsyncClient):
        endpoints = [
            "/api/admin/users",
            "/api/admin/stats",
        ]

        for endpoint in endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 401, f"Endpoint {endpoint} should require authentication"

    @pytest.mark.asyncio
    async def test_superuser_can_view_specific_user(
        self, client: AsyncClient, superuser_token: str, regular_user: User
    ):
        response = await client.get(
            f"/api/admin/users/{regular_user.id}",
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == regular_user.email

    @pytest.mark.asyncio
    async def test_regular_user_cannot_view_other_users(
        self, client: AsyncClient, regular_user_token: str, superuser: User
    ):
        response = await client.get(
            f"/api/admin/users/{superuser.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403
