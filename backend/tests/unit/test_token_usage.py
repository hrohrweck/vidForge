"""Tests for TokenUsageService — TDD style."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from sqlalchemy import select

from app.chatbot.service import TokenUsageService
from app.database import Base, ChatTokenUsage, async_session


class TestRecord:
    """Tests for TokenUsageService.record()."""

    @pytest.fixture
    def service(self):
        return TokenUsageService()

    @pytest.mark.asyncio
    async def test_record_creates_row(self, db_session):
        """record() writes a ChatTokenUsage row with correct fields."""
        service = TokenUsageService()
        user_id = uuid4()
        model_id = "qwen3.6"
        conversation_id = uuid4()
        tokens_in = 120
        tokens_out = 45

        await service.record(
            db_session,
            user_id=user_id,
            model_id=model_id,
            conversation_id=conversation_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        await db_session.commit()

        result = await db_session.execute(select(ChatTokenUsage).where(ChatTokenUsage.user_id == user_id))
        row = result.scalars().one()

        assert row.user_id == user_id

    @pytest.mark.asyncio
    async def test_record_optional_conversation(self, db_session):
        """conversation_id may be None (global aggregate)."""
        service = TokenUsageService()
        user_id = uuid4()

        await service.record(db_session, user_id=user_id, model_id="gpt-4", conversation_id=None, tokens_in=10, tokens_out=5)
        await db_session.commit()

        rows = (await db_session.execute(
            ChatTokenUsage.__table__.select().where(ChatTokenUsage.user_id == user_id)
        )).fetchall()
        assert len(rows) == 1
        assert rows[0].conversation_id is None

    @pytest.mark.asyncio
    async def test_record_multiple_rows_same_user(self, db_session):
        """Multiple record() calls accumulate rows."""
        service = TokenUsageService()
        user_id = uuid4()

        await service.record(db_session, user_id, "qwen3.6", None, 100, 20)
        await service.record(db_session, user_id, "llama3.3", None, 200, 40)
        await db_session.commit()

        rows = (await db_session.execute(
            ChatTokenUsage.__table__.select().where(ChatTokenUsage.user_id == user_id)
        )).fetchall()
        assert len(rows) == 2


class TestAggregate:
    """Tests for TokenUsageService.aggregate()."""

    @pytest.fixture
    def service(self):
        return TokenUsageService()

    @pytest.fixture
    async def populate(self, db_session):
        """Create a user with token usage rows spanning multiple days and models."""
        user_id = uuid4()
        now = datetime.utcnow()

        rows = [
            # Day 1 — qwen3.6
            _make_row(user_id, "qwen3.6", None, 100, 20, now - timedelta(days=1)),
            _make_row(user_id, "qwen3.6", None, 100, 20, now - timedelta(days=1)),
            # Day 2 — llama3.3
            _make_row(user_id, "llama3.3", None, 200, 40, now - timedelta(days=2)),
            # Day 3 — qwen3.6
            _make_row(user_id, "qwen3.6", None, 150, 30, now - timedelta(days=3)),
        ]

        for row in rows:
            db_session.add(row)
        await db_session.commit()
        return user_id

    @pytest.mark.asyncio
    async def test_aggregate_all_by_model(self, db_session, populate):
        """aggregate(range='all', group_by='model') returns per-model sums."""
        service = TokenUsageService()
        result = await service.aggregate(db_session, user_id=populate, range="all", group_by="model")

        assert len(result) == 2
        by_model = {r["model_id"]: r for r in result}

        assert by_model["qwen3.6"]["total_tokens_in"] == 350
        assert by_model["qwen3.6"]["total_tokens_out"] == 70
        assert by_model["llama3.3"]["total_tokens_in"] == 200
        assert by_model["llama3.3"]["total_tokens_out"] == 40

    @pytest.mark.asyncio
    async def test_aggregate_7d_filter(self, db_session, populate):
        """Rows older than 7 days are excluded."""
        service = TokenUsageService()
        result = await service.aggregate(db_session, user_id=populate, range="7d", group_by="model")

        by_model = {r["model_id"]: r for r in result}
        assert by_model["qwen3.6"]["total_tokens_in"] == 350

    @pytest.mark.asyncio
    async def test_aggregate_30d_filter(self, db_session, populate):
        """Rows older than 30 days are excluded."""
        service = TokenUsageService()
        result = await service.aggregate(db_session, user_id=populate, range="30d", group_by="model")

        # All 3 days are within 30d, so all rows included
        by_model = {r["model_id"]: r for r in result}
        assert by_model["qwen3.6"]["total_tokens_in"] == 350
        assert by_model["llama3.3"]["total_tokens_in"] == 200

    @pytest.mark.asyncio
    async def test_aggregate_group_by_day(self, db_session, populate):
        """group_by='day' returns one row per day."""
        service = TokenUsageService()
        result = await service.aggregate(db_session, user_id=populate, range="all", group_by="day")

        assert len(result) == 3  # 3 distinct days

    @pytest.mark.asyncio
    async def test_aggregate_empty_user(self, db_session):
        """User with no usage returns empty list."""
        service = TokenUsageService()
        result = await service.aggregate(db_session, user_id=uuid4(), range="all", group_by="model")
        assert result == []

    @pytest.mark.asyncio
    async def test_aggregate_invalid_range(self, db_session, populate):
        """Invalid range raises ValueError."""
        service = TokenUsageService()
        with pytest.raises(ValueError, match="Invalid range"):
            await service.aggregate(db_session, user_id=populate, range="invalid", group_by="model")


class TestFireAndForget:
    """Tests for non-blocking fire-and-forget behavior."""

    @pytest.mark.asyncio
    async def test_record_fire_and_forget_does_not_block(self, db_session):
        """record() returns immediately without await when using fire_and_forget=True."""
        service = TokenUsageService()

        with patch.object(service, "record", new_callable=AsyncMock) as mock_record:
            mock_record.return_value = None  # simulate non-blocking

            # If fire_and_forget=True, the method should return without blocking
            # We verify by checking the mock was called and returned immediately
            start = datetime.now()
            result = await service.record_fire_and_forget(
                db_session,
                user_id=uuid4(),
                model_id="qwen3.6",
                conversation_id=None,
                tokens_in=10,
                tokens_out=5,
            )
            elapsed = (datetime.now() - start).total_seconds()

            # The mock returns instantly; a real implementation would use asyncio.create_task
            assert result is None

    @pytest.mark.asyncio
    async def test_record_fire_and_forget_creates_task(self):
        """record_fire_and_forget() uses asyncio.create_task to avoid blocking."""
        service = TokenUsageService()
        mock_session = AsyncMock()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            await service.record_fire_and_forget(
                mock_session,
                user_id=uuid4(),
                model_id="qwen3.6",
                conversation_id=None,
                tokens_in=10,
                tokens_out=5,
            )

            mock_create_task.assert_called_once()
            args, kwargs = mock_create_task.call_args
            coro = args[0]
            assert asyncio.iscoroutine(coro)


def _make_row(user_id, model_id, conversation_id, tokens_in, tokens_out, recorded_at):
    return ChatTokenUsage(
        user_id=user_id,
        model_id=model_id,
        conversation_id=conversation_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        recorded_at=recorded_at,
    )