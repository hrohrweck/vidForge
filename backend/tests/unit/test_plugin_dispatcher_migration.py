from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.database import Job, Template


class _Result:
    def __init__(self, value=None) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Session:
    def __init__(self, job, template) -> None:
        print(f"DEBUG: _SessionFactory init job={type(job)}")
        self.job = job
        self.template = template

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, statement):
        descriptions = getattr(statement, "column_descriptions", None)
        entity = descriptions[0].get("entity") if descriptions else None
        entity_name = getattr(entity, "__name__", None)
        if entity is Template or entity_name == "Template":
            return _Result(self.template)
        if entity is Job or entity_name == "Job":
            return _Result(self.job)
        return _Result(None)

    async def commit(self):
        return None

    async def refresh(self, instance):
        return None


class _SessionFactory:
    def __init__(self, job, template) -> None:
        print(f"DEBUG: _SessionFactory init job={type(job)}")
        self.job = job
        self.template = template

    def __call__(self):
        return _Session(self.job, self.template)


def _job(job_id, template_id):
    return SimpleNamespace(
        id=job_id,
        user_id=uuid4(),
        template_id=template_id,
        input_data={"prompt": "test", "generate_audio": True},
        provider_preference="auto",
        provider_id=None,
        provider_type=None,
        estimated_cost=None,
        workflow_type=None,
        output_path=None,
        preview_path=None,
        chat_conversation_id=None,
        chat_message_id=None,
    )


def _template(template_id):
    return SimpleNamespace(
        id=template_id,
        name="prompt_to_video",
        config={"plugin_id": "prompt_to_video", "workflow_type": "scene_based"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type", ["comfyui_direct", "runpod", "poe"])
async def test_process_video_job_routes_every_provider_through_dispatcher(
    monkeypatch, provider_type
):
    from app.workers import context
    from app.workers import dispatcher as dispatcher_module
    from app.workers import tasks as tasks_module

    job_id = uuid4()
    template_id = uuid4()
    job = _job(job_id, template_id)
    template = _template(template_id)
    session_factory = _SessionFactory(job, template)

    for worker_ctx in {context.ctx, dispatcher_module.ctx, tasks_module.ctx}:
        monkeypatch.setattr(worker_ctx, "_session_factory", session_factory)

    async def no_status_update(*args, **kwargs):
        return None

    provider = SimpleNamespace(
        id=uuid4(),
        provider_type=provider_type,
        config={"max_concurrent_jobs": 0},
    )

    async def resolve_provider(*args, **kwargs):
        return provider, SimpleNamespace(), 0, None, "test"

    class FakeBudgetTracker:
        def __init__(self, db):
            self.db = db

        async def record_spend(self, *args, **kwargs):
            return None

    stages: list[str] = []

    async def fake_dispatch_stage(dispatched_job_id: str, stage: str):
        assert dispatched_job_id == str(job_id)
        stages.append(stage)
        if stage == "rendering":
            job.output_path = "output/final.mp4"
            job.preview_path = "output/preview.mp4"
        return {"status": "completed", "job_id": dispatched_job_id, "stage": stage}

    monkeypatch.setattr(tasks_module, "update_job_status", no_status_update)
    monkeypatch.setattr(tasks_module, "_resolve_provider_for_job", resolve_provider)
    monkeypatch.setattr(tasks_module, "BudgetTracker", FakeBudgetTracker)
    monkeypatch.setattr(dispatcher_module, "dispatch_stage", fake_dispatch_stage)

    try:
        print(f"DEBUG: tasks_module.ctx={id(tasks_module.ctx)}, context.ctx={id(context.ctx)}")
        try:
            result = await tasks_module._process_video_job(str(job_id), "auto")
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise

    assert result == {"status": "completed", "job_id": str(job_id)}
    assert stages == ["planning", "generating_images", "generating_videos", "rendering"]
    assert job.provider_type == provider_type
    assert job.workflow_type == "scene_based"


@pytest.mark.asyncio
async def test_prompt_to_video_generate_audio_runs_before_render(monkeypatch, tmp_path):
    from app.plugins.media_stages import MediaStagesMixin
    from plugins.prompt_to_video.plugin import PromptToVideoPlugin

    generated: dict[str, object] = {}
    rendered_context: dict[str, object] = {}

    class FakeMusicGenService:
        async def is_available(self):
            return True

        async def generate(self, **kwargs):
            generated.update(kwargs)
            return str(tmp_path / "background_music.mp3")

    async def fake_render(self, db, job, scenes, context):
        rendered_context.update(context)
        return {"output_path": "output/final.mp4", "preview_path": "output/preview.mp4"}

    monkeypatch.setattr(
        "app.services.audio_generation.MusicGenService",
        FakeMusicGenService,
    )
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(storage_path=str(tmp_path)),
    )
    monkeypatch.setattr(MediaStagesMixin, "render", fake_render)

    job = SimpleNamespace(
        id=uuid4(),
        input_data={
            "prompt": "cinematic sunrise",
            "generate_audio": True,
            "duration": 12,
            "audio_volume": 0.4,
        },
    )

    result = await PromptToVideoPlugin().render(None, job, [], {})

    assert result["output_path"] == "output/final.mp4"
    assert generated["prompt"] == "cinematic sunrise"
    assert generated["duration"] == 12
    assert generated["output_format"] == "mp3"
    assert rendered_context["background_music"] == str(tmp_path / "background_music.mp3")
    assert rendered_context["background_music_volume"] == 0.4
