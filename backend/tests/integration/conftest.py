"""Integration test fixtures.

These tests require a running PostgreSQL database and Redis instance.
Set DATABASE_URL and REDIS_URL environment variables to point to real services.
By default they use the same defaults as the app (localhost).
"""

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Base, Template, get_db
from app.main import app

INTEGRATION_DATABASE_URL = os.environ.get(
    "INTEGRATION_DATABASE_URL",
    "postgresql+asyncpg://vidforge:vidforge@localhost:5432/vidforge_test",
)


def _check_postgres_available() -> bool:
    """Check if PostgreSQL is reachable at the configured URL."""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(INTEGRATION_DATABASE_URL.replace("+asyncpg", ""))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect((host, port))
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        sock.close()


@pytest.fixture(scope="session", autouse=True)
def skip_if_no_postgres():
    """Skip all integration tests if PostgreSQL is not available."""
    if not _check_postgres_available():
        pytest.skip(
            f"PostgreSQL not available at {INTEGRATION_DATABASE_URL} — skipping integration tests",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    """Override event_loop to session scope so engine pool stays on same loop."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def integration_engine_fixture():
    """Session-scoped engine with NullPool to avoid cross-loop connection issues."""
    engine = create_async_engine(
        INTEGRATION_DATABASE_URL, echo=False, poolclass=NullPool
    )
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def setup_database(integration_engine_fixture):
    """Create all tables and seed a default template once per session."""
    engine = integration_engine_fixture
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed_session:
        seed_session.add(
            Template(
                id=uuid4(),
                name="Avatar Test Template",
                description="Seeded template for integration tests",
                config={
                    "inputs": [{"name": "prompt", "type": "text", "required": True}],
                    "workflow_type": "direct",
                },
                is_builtin=True,
            )
        )
        await seed_session.commit()

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(setup_database):
    engine = setup_database
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def integration_client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
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
