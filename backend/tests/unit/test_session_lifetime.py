from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.database import Job, Template


class SessionTracker:
    def __init__(self) -> None:
        self.current = 0
        self.max_seen = 0
        self.open_during_generation = False

    def opened(self) -> None:
        self.current += 1
        self.max_seen = max(self.max_seen, self.current)

    def closed(self) -> None:
        self.current -= 1


class _Result:
    def __init__(self, value=None, values=None) -> None:
        self._value = value
        self._values = values or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        values = self._values

        class _Scalars:
            def all(self):
                return values

        return _Scalars()


class TrackingSession:
    def __init__(self, tracker: SessionTracker, job, template, scenes=None) -> None:
        self.tracker = tracker
        self.job = job
        self.template = template
        self.scenes = scenes or []

    async def __aenter__(self):
        self.tracker.opened()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.tracker.closed()

    async def execute(self, statement):
        entity = None
        descriptions = getattr(statement, "column_descriptions", None)
        if descriptions:
            entity = descriptions[0].get("entity")
        entity_name = getattr(entity, "__name__", None)
        if entity is Job or entity_name == "Job":
            return _Result(self.job)
        if entity is Template or entity_name == "Template":
            return _Result(self.template)
        return _Result(values=self.scenes)

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None

    def add(self, obj):
        return None


class TrackingSessionFactory:
    def __init__(self, tracker: SessionTracker, job, template, scenes=None) -> None:
        self.tracker = tracker
        self.job = job
        self.template = template
        self.scenes = scenes or []

    def __call__(self):
        return TrackingSession(self.tracker, self.job, self.template, self.scenes)


def _job(job_id, template_id, provider_preference="auto"):
    return SimpleNamespace(
        id=job_id,
        user_id=uuid4(),
        template_id=template_id,
        input_data={"prompt": "test"},
        provider_preference=provider_preference,
        provider_id=None,
        provider_type=None,
        estimated_cost=None,
        image_provider_id=None,
        workflow_type=None,
        status="pending",
        stage="queued",
        progress=0,
        output_path="final.mp4",
        preview_path="preview.jpg",
        error_message=None,
        chat_conversation_id=None,
        chat_message_id=None,
        project_id=None,
        title="Test job",
    )


def _template(template_id):
    return SimpleNamespace(
        id=template_id,
        name="prompt_to_video",
        config={"plugin_id": "prompt_to_video"},
    )


@pytest.mark.asyncio
async def test_process_video_job_does_not_hold_outer_session_during_dispatch_generation(monkeypatch):
    from app.workers import context
    from app.workers import dispatcher as dispatcher_module
    from app.workers import tasks as tasks_module

    tracker = SessionTracker()
    job_id = uuid4()
    template_id = uuid4()
    job = _job(job_id, template_id)
    template = _template(template_id)
    session_factory = TrackingSessionFactory(tracker, job, template)
    for worker_ctx in {context.ctx, tasks_module.ctx, dispatcher_module.ctx}:
        monkeypatch.setattr(worker_ctx, "_session_factory", session_factory)

    async def no_status_update(*args, **kwargs):
        return None

    provider = SimpleNamespace(
        id=uuid4(),
        provider_type="poe",
        config={"max_concurrent_jobs": 0},
    )
    provider_instance = SimpleNamespace()

    async def resolve_provider(*args, **kwargs):
        return provider, provider_instance, 0, None, "test"

    class FakeBudgetTracker:
        def __init__(self, db):
            self.db = db

        async def check_budget(self, provider_id, amount):
            return (True, "")

    async def fake_estimate_job_cost(*args, **kwargs):
        return SimpleNamespace(total=Decimal("0"))

    async def fake_get_job_actual_cost(*args, **kwargs):
        return Decimal("0")

    monkeypatch.setattr(
        "app.services.cost_estimator.estimate_job_cost", fake_estimate_job_cost
    )
    monkeypatch.setattr(
        "app.services.cost_estimator.get_job_actual_cost", fake_get_job_actual_cost
    )

    async def fake_dispatch_stage(dispatched_job_id: str, stage: str):
        assert dispatched_job_id == str(job_id)
        if stage in {"generating_images", "generating_videos"}:
            if tracker.current:
                tracker.open_during_generation = True
            await asyncio.sleep(0)
        return {"status": "completed", "job_id": dispatched_job_id, "stage": stage}

    monkeypatch.setattr(tasks_module, "update_job_status", no_status_update)
    monkeypatch.setattr(tasks_module, "_resolve_provider_for_job", resolve_provider)
    monkeypatch.setattr(tasks_module, "BudgetTracker", FakeBudgetTracker)
    monkeypatch.setattr(dispatcher_module, "dispatch_stage", fake_dispatch_stage)

    result = await tasks_module._process_video_job(str(job_id), "auto")

    assert result == {"status": "completed", "job_id": str(job_id)}
    assert tracker.max_seen <= 2
    assert tracker.open_during_generation is True
