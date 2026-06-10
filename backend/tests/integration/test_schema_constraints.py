"""Integration tests for schema constraints (indexes and unique constraints).

Verifies:
- Indexes exist on expected columns
- UniqueConstraint on VideoScene(job_id, scene_number) works
- CostLog indexes exist
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.database import (
    CostLog,
    Job,
    ModelConfig,
    Provider,
    Template,
    User,
    VideoScene,
)


@pytest.fixture
async def test_provider(db_session):
    provider = Provider(
        id=uuid4(),
        name="schema-test-provider",
        provider_type="poe",
        config={"api_key": "test"},
    )
    db_session.add(provider)
    await db_session.flush()
    return provider


@pytest.fixture
async def test_user(db_session):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        id=uuid4(),
        email="schema-test@example.com",
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_job(db_session, test_user, test_provider):
    job = Job(
        id=uuid4(),
        user_id=test_user.id,
        status="pending",
        input_data={"prompt": "test"},
    )
    db_session.add(job)
    await db_session.flush()
    return job


class TestSchemaIndexes:
    async def test_job_user_id_index(self, db_session):
        indexes = await db_session.run_sync(
            lambda sync_session: inspect(sync_session.bind).get_indexes("jobs")
        )
        index_names = {idx["name"] for idx in indexes}
        assert "ix_jobs_user_id" in index_names, f"Got indexes: {index_names}"

    async def test_job_created_at_index(self, db_session):
        indexes = await db_session.run_sync(
            lambda sync_session: inspect(sync_session.bind).get_indexes("jobs")
        )
        index_names = {idx["name"] for idx in indexes}
        assert "ix_jobs_created_at" in index_names, f"Got indexes: {index_names}"

    async def test_model_config_model_id_index(self, db_session):
        indexes = await db_session.run_sync(
            lambda sync_session: inspect(sync_session.bind).get_indexes("model_configs")
        )
        index_names = {idx["name"] for idx in indexes}
        assert "ix_model_configs_model_id" in index_names, f"Got indexes: {index_names}"

    async def test_chat_token_usage_user_id_index(self, db_session):
        indexes = await db_session.run_sync(
            lambda sync_session: inspect(sync_session.bind).get_indexes("chat_token_usage")
        )
        index_names = {idx["name"] for idx in indexes}
        assert "ix_chat_token_usage_user_id" in index_names, f"Got indexes: {index_names}"

    async def test_cost_log_indexes(self, db_session):
        indexes = await db_session.run_sync(
            lambda sync_session: inspect(sync_session.bind).get_indexes("cost_log")
        )
        index_names = {idx["name"] for idx in indexes}
        assert "ix_cost_log_provider_id" in index_names, f"Got indexes: {index_names}"
        assert "ix_cost_log_job_id" in index_names, f"Got indexes: {index_names}"
        assert "ix_cost_log_created_at" in index_names, f"Got indexes: {index_names}"


class TestVideoSceneUniqueConstraint:
    async def test_duplicate_scene_number_raises_integrity_error(
        self, db_session, test_job
    ):
        scene1 = VideoScene(
            id=uuid4(),
            job_id=test_job.id,
            scene_number=1,
            start_time=0.0,
            end_time=5.0,
        )
        db_session.add(scene1)
        await db_session.flush()

        scene2 = VideoScene(
            id=uuid4(),
            job_id=test_job.id,
            scene_number=1,
            start_time=5.0,
            end_time=10.0,
        )
        db_session.add(scene2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_different_jobs_same_scene_number_allowed(
        self, db_session, test_user, test_provider
    ):
        job1 = Job(
            id=uuid4(),
            user_id=test_user.id,
            status="pending",
            input_data={"prompt": "test1"},
        )
        job2 = Job(
            id=uuid4(),
            user_id=test_user.id,
            status="pending",
            input_data={"prompt": "test2"},
        )
        db_session.add_all([job1, job2])
        await db_session.flush()

        scene1 = VideoScene(
            id=uuid4(),
            job_id=job1.id,
            scene_number=1,
            start_time=0.0,
            end_time=5.0,
        )
        scene2 = VideoScene(
            id=uuid4(),
            job_id=job2.id,
            scene_number=1,
            start_time=0.0,
            end_time=5.0,
        )
        db_session.add_all([scene1, scene2])
        await db_session.flush()
