import os
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models.app_settings  # noqa: F401
import app.models.media  # noqa: F401
from app.api.auth import create_access_token
from app.database import Base, Conversation, Job, Template, User, get_db
from app.main import app

# Ensure a valid SECRET_KEY is present for tests so config validation passes
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-not-for-production")

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


def patch_jsonb_for_sqlite():
    """Replace JSONB with JSON for SQLite compatibility."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if hasattr(column.type, "__class__") and column.type.__class__.__name__ == "JSONB":
                column.type = JSON()


@pytest.fixture(scope="function")
async def db_session():
    patch_jsonb_for_sqlite()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mocker():
    """Compatibility fixture for tests that expect pytest-mock's mocker fixture."""

    from unittest.mock import patch

    patches: list = []

    class Mocker:
        def magic_mock(self, *args, **kwargs):
            return MagicMock(*args, **kwargs)

        # Backward compatibility alias
        MagicMock = magic_mock

        def patch(self, target, *args, **kwargs):
            patcher = patch(target, *args, **kwargs)
            started = patcher.start()
            patches.append(patcher)
            return started

    mock = Mocker()
    try:
        yield mock
    finally:
        for patcher in reversed(patches):
            patcher.stop()


@pytest.fixture
async def client(db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
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
    return create_access_token(data={"sub": str(regular_user.id)})


@pytest.fixture
def superuser_token(superuser):
    return create_access_token(data={"sub": str(superuser.id)})


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
async def conversation(db_session: AsyncSession):
    conversation = Conversation(
        id=uuid4(),
        title="Test Conversation",
        model_id="test-model",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest.fixture
async def job_for_user(db_session: AsyncSession, regular_user: User, template: Template):
    job = Job(
        id=uuid4(),
        user_id=regular_user.id,
        template_id=template.id,
        status="pending",
        input_data={"prompt": "test"},
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job
