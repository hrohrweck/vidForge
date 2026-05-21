"""Integration test fixtures.

These tests require a running PostgreSQL database and Redis instance.
Set DATABASE_URL and REDIS_URL environment variables to point to real services.
By default they use the same defaults as the app (localhost).
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

# Use real PostgreSQL for integration tests
INTEGRATION_DATABASE_URL = os.environ.get(
    "INTEGRATION_DATABASE_URL",
    "postgresql+asyncpg://vidforge:vidforge@localhost:5432/vidforge_test",
)

integration_engine = create_async_engine(INTEGRATION_DATABASE_URL, echo=False)
IntegrationSessionFactory = async_sessionmaker(
    integration_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def setup_database():
    """Create all tables once for the test session."""
    async with integration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with integration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(setup_database):
    async with IntegrationSessionFactory() as session:
        yield session


@pytest.fixture
async def integration_client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def registered_user(integration_client: AsyncClient):
    """Register a user and return user data with token."""
    response = await integration_client.post(
        "/api/auth/register",
        json={"email": "integration@test.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    data = response.json()
    return {"id": data["id"], "email": data["email"], "token": None}


@pytest.fixture
async def authenticated_client(integration_client: AsyncClient):
    """Register + login, return client with auth headers."""
    await integration_client.post(
        "/api/auth/register",
        json={"email": "integration@test.com", "password": "testpass123"},
    )
    response = await integration_client.post(
        "/api/auth/login",
        json={"email": "integration@test.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    integration_client.headers["Authorization"] = f"Bearer {token}"
    return integration_client
