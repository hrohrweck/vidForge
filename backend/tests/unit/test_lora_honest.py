from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token
from app.database import Avatar, User
from app.main import app


@pytest.fixture
async def regular_user(db_session: AsyncSession):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        id=uuid4(),
        email="test@example.com",
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def regular_user_token(regular_user):
    return create_access_token(data={"sub": str(regular_user.id)})


@pytest.fixture
async def avatar(db_session: AsyncSession, regular_user: User):
    avatar = Avatar(
        id=uuid4(),
        user_id=regular_user.id,
        name="Test Avatar",
        gender="Female",
        bio="A test character",
        consistency_strategy="lora",
        lora_training_status="not_trained",
    )
    db_session.add(avatar)
    await db_session.commit()
    await db_session.refresh(avatar)
    return avatar


class TestLoraHonest:
    async def test_train_lora_endpoint_returns_501(self, client, regular_user_token, avatar):
        response = await client.post(
            f"/api/avatars/{avatar.id}/train-lora",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 501
        data = response.json()
        detail = data.get("detail", "").lower()
        assert "not available" in detail or "not yet available" in detail

    async def test_task_sets_unavailable_and_no_fake_path(self, db_session, avatar):
        from app.workers.tasks import _train_avatar_lora

        mock_ctx = MagicMock()
        mock_ctx.session_factory.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.tasks.ctx", mock_ctx):
            result = await _train_avatar_lora(str(avatar.id))

        assert result["status"] == "completed"
        assert result["avatar_id"] == str(avatar.id)

        from sqlalchemy import select
        from app.database import Avatar as AvatarModel

        result = await db_session.execute(
            select(AvatarModel).where(AvatarModel.id == avatar.id)
        )
        refreshed = result.scalar_one()

        assert refreshed.lora_training_status == "unavailable"
        assert refreshed.lora_model_path is None

    async def test_task_logs_warning(self, db_session, avatar, caplog):
        import logging

        from app.workers.tasks import _train_avatar_lora

        mock_ctx = MagicMock()
        mock_ctx.session_factory.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.tasks.ctx", mock_ctx):
            with caplog.at_level(logging.WARNING, logger="app.workers.tasks"):
                await _train_avatar_lora(str(avatar.id))

        assert any(
            "not implemented" in record.message.lower() or "unavailable" in record.message.lower()
            for record in caplog.records
        )
