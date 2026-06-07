"""Integration tests for the object consistency pipeline.

Covers:
- T12: Full pipeline — enrich_inputs → plan_scenes → generate_images → generate_videos
- T13: Priority-based object selection with limited reference capacity
- T14: Error handling (no objects, invalid JSON, failed generation, missing fields)

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/test_object_pipeline.py -v
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, JobObjectRef, ObjectRef, ObjectRefImage, User, VideoScene
from app.plugins.base import PluginBase

pytestmark = pytest.mark.integration

# ──────────────────────────────────────────────────────────────────────
# Test plugin that simulates a planner returning object_selections
# ──────────────────────────────────────────────────────────────────────


class ObjectPipelineTestPlugin(PluginBase):
    """Plugin that simulates a planner aware of object selections."""

    @property
    def plugin_id(self) -> str:
        return "object_pipeline_test"

    @property
    def display_name(self) -> str:
        return "Object Pipeline Test"

    @property
    def description(self) -> str:
        return "Test plugin for object consistency pipeline integration tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        """Create scenes and return object_selections."""
        objects = context.get("objects", [])
        avatars = context.get("avatars", [])
        avatar_name = avatars[0]["name"] if avatars else "Unknown"

        scene = VideoScene(
            id=uuid4(),
            job_id=job.id,
            scene_number=1,
            start_time=0.0,
            end_time=5.0,
            visual_description=f"Scene with {avatar_name}",
            image_prompt=f"Cinematic shot of {avatar_name} in action",
            status="pending",
        )
        db.add(scene)
        await db.commit()

        # Build object_selections based on the objects in context
        selections = []
        for i, obj in enumerate(objects):
            selections.append({
                "object_name": obj["name"],
                "importance_score": 0.9 - (i * 0.3),
                "seed_image_prompt": f"Reference image of {obj['name']}",
                "scenes": [1],
            })

        return {"scene_count": 1, "object_selections": selections}


# ──────────────────────────────────────────────────────────────────────
# Test plugin for priority-limited capacity tests (T13)
# ──────────────────────────────────────────────────────────────────────


class PriorityTestPlugin(PluginBase):
    """Plugin that simulates limited reference capacity selection."""

    @property
    def plugin_id(self) -> str:
        return "priority_test"

    @property
    def display_name(self) -> str:
        return "Priority Test"

    @property
    def description(self) -> str:
        return "Test plugin for priority-based selection"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        """Only select the highest-priority object when capacity is limited."""
        objects = context.get("objects", [])

        scene = VideoScene(
            id=uuid4(),
            job_id=job.id,
            scene_number=1,
            start_time=0.0,
            end_time=5.0,
            visual_description="Test scene",
            image_prompt="Test image prompt",
            status="pending",
        )
        db.add(scene)
        await db.commit()

        # Simulate limited capacity: only select 1 object (the most important)
        selections = []
        if objects:
            top = objects[0]  # First object is most important
            selections = [{
                "object_name": top["name"],
                "importance_score": 0.9,
                "seed_image_prompt": f"Reference image of {top['name']}",
                "scenes": [1],
            }]

        return {"scene_count": 1, "object_selections": selections}


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

LLM_RESPONSE_CHARS_AND_OBJECTS = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A fearless driver with a love for speed.", '
    '"role": "Lead driver"}],'
    '"objects": ['
    '{"name": "Ferrari", "description": "A gleaming red Italian sports car", '
    '"visual_properties": {"color": "red", "make": "Ferrari", "model": "488 GTB", '
    '"distinctive_features": "sleek curves, racing stripe"}, '
    '"role": "The main vehicle, appears in every driving scene"}]}'
)

LLM_RESPONSE_CHARS_ONLY = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A fearless driver.", "role": "Lead"}],'
    '"objects": []}'
)

LLM_RESPONSE_NO_JSON = "Just some text about a car chase, not valid JSON at all."

LLM_RESPONSE_MULTIPLE_OBJECTS = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A getaway driver.", "role": "Driver"}],'
    '"objects": ['
    '{"name": "Ferrari", "description": "Red Italian sports car", '
    '"visual_properties": {"color": "red", "make": "Ferrari"}, '
    '"role": "Main vehicle"},'
    '{"name": "Watch", "description": "Gold wristwatch with chronograph", '
    '"visual_properties": {"color": "gold", "make": "Rolex"}, '
    '"role": "Shows time pressure"},'
    '{"name": "Sunglasses", "description": "Black aviator sunglasses", '
    '"visual_properties": {"color": "black", "style": "aviator"}, '
    '"role": "Worn when driving"}]}'
)

LLM_RESPONSE_OBJECT_NO_VISUAL_PROPS = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A detective.", "role": "Detective"}],'
    '"objects": ['
    '{"name": "Notebook", "description": "A worn leather notebook", '
    '"role": "Used for case notes"}]}'
)

PATCH_LLM = "app.services.llm_service.LLMClient"
PATCH_GEN_IMAGE = "app.services.media_generator.generate_image"
PATCH_GEN_VIDEO = "app.services.media_generator.generate_video"
PATCH_PREFS = "app.api.models.get_default_model_preferences"


def _make_test_user(email):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return User(
        id=uuid4(),
        email=email,
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )


def _make_gen_image_mock(tmp_dir):
    async def _gen(*, db, job, prompt, scene_number,
                    model_preference=None, aspect_ratio="3:2",
                    title=None, reference_image_path=None,
                    reference_image_strength=0.75,
                    lora_path=None, lora_strength=0.8,
                    provider_id=None, **kwargs):
        fname = f"{title or 'img'}_{scene_number}.png"
        fpath = os.path.join(tmp_dir, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4())
    return AsyncMock(side_effect=_gen)


def _make_gen_video_mock(tmp_dir):
    async def _gen(*, db, job, prompt, scene_number,
                    reference_image_path=None, provider_id=None,
                    model_preference=None, duration=5,
                    aspect_ratio="16:9", title=None, **kwargs):
        fname = f"video_s{scene_number}.mp4"
        fpath = os.path.join(tmp_dir, fname)
        Path(fpath).write_bytes(
            b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41"
            b"\x00\x00\x00\x08free" + b"\x00" * 500
        )
        return (fname, "test-video-model", uuid4(), 5.0, None)
    return AsyncMock(side_effect=_gen)


async def _cleanup_objects(db_session, user_id):
    from sqlalchemy import delete as sa_delete
    await db_session.execute(
        sa_delete(JobObjectRef).where(
            JobObjectRef.object_ref_id.in_(
                select(ObjectRef.id).where(ObjectRef.user_id == user_id)
            )
        )
    )
    await db_session.execute(
        sa_delete(ObjectRefImage).where(
            ObjectRefImage.object_ref_id.in_(
                select(ObjectRef.id).where(ObjectRef.user_id == user_id)
            )
        )
    )
    await db_session.execute(
        sa_delete(ObjectRef).where(ObjectRef.user_id == user_id)
    )


async def _cleanup_avatars(db_session, user_id):
    from sqlalchemy import delete as sa_delete, update as sa_update
    from app.database import Avatar, AvatarImage
    await db_session.execute(
        sa_update(Avatar).where(Avatar.user_id == user_id).values(primary_image_id=None)
    )
    await db_session.execute(
        sa_delete(AvatarImage).where(
            AvatarImage.avatar_id.in_(
                select(Avatar.id).where(Avatar.user_id == user_id)
            )
        )
    )
    await db_session.execute(sa_delete(Avatar).where(Avatar.user_id == user_id))


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.storage_path = tmp
            yield tmp


@pytest.fixture
def no_sleep():
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep


# ══════════════════════════════════════════════════════════════════════
# T12: Full object consistency pipeline
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_full_object_pipeline_enrich_to_video(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    """T12: Full pipeline — LLM returns chars+objects → enrich → plan → generate.

    Asserts:
    - ObjectRef + JobObjectRef created during enrich_inputs
    - context["objects"] populated with resolved dicts (no primary_image_path yet)
    - plan_scenes returns object_selections
    - _generate_object_references generates images for selected objects
    - generate_images injects object visual properties into prompts
    - generate_videos receives reference_image_path
    """
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"obj_full_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(),
        user_id=user.id,
        status="pending",
        input_data={"prompt": "A high-speed car chase through Monaco"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = ObjectPipelineTestPlugin()
    gen_image_mock = _make_gen_image_mock(temp_storage)
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=LLM_RESPONSE_CHARS_AND_OBJECTS)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    # ── Stage 1: enrich_inputs ──
    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    # Assert characters created
    assert "avatars" in context
    assert len(context["avatars"]) == 1
    assert context["avatars"][0]["name"] == "Alice"

    # Assert objects detected and persisted
    assert "objects" in context
    assert len(context["objects"]) == 1
    assert context["objects"][0]["name"] == "Ferrari"
    assert context["objects"][0]["visual_properties"]["color"] == "red"
    # Object images are deferred — no primary_image_path yet
    assert context["objects"][0]["primary_image_path"] is None

    # Assert ObjectRef persisted in DB
    result = await db_session.execute(
        select(ObjectRef).where(ObjectRef.user_id == user.id)
    )
    obj_refs = result.scalars().all()
    assert len(obj_refs) == 1
    assert obj_refs[0].name == "Ferrari"
    assert obj_refs[0].visual_properties is not None
    assert obj_refs[0].visual_properties["color"] == "red"

    # Assert JobObjectRef created
    result = await db_session.execute(
        select(JobObjectRef).where(JobObjectRef.job_id == job.id)
    )
    job_obj_refs = result.scalars().all()
    assert len(job_obj_refs) == 1
    assert job_obj_refs[0].object_ref_id == obj_refs[0].id

    # ── Stage 2: plan_scenes ──
    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        plan_context = await plugin.plan_scenes(db_session, job, context)

    assert "object_selections" in plan_context
    assert len(plan_context["object_selections"]) == 1
    assert plan_context["object_selections"][0]["object_name"] == "Ferrari"
    assert plan_context["object_selections"][0]["importance_score"] == 0.9

    # Merge plan_context into main context for subsequent stages
    context.update(plan_context)

    # ── Stage 3: generate_images ──
    result = await db_session.execute(
        select(VideoScene).where(VideoScene.job_id == job.id)
    )
    scenes = list(result.scalars().all())
    assert len(scenes) == 1

    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.generate_images(db_session, job, scenes, context)

    await db_session.refresh(scenes[0])
    assert scenes[0].status == "image_ready"
    assert scenes[0].reference_image_path is not None

    # Assert ObjectRefImage was created (deferred generation happened)
    result = await db_session.execute(
        select(ObjectRefImage).where(ObjectRefImage.object_ref_id == obj_refs[0].id)
    )
    obj_images = result.scalars().all()
    assert len(obj_images) == 1
    assert obj_images[0].is_primary is True

    # Assert object visual properties were injected into the scene image prompt
    gen_image_call_args = gen_image_mock.call_args_list[-1].kwargs
    prompt_used = gen_image_call_args.get("prompt", "")
    assert "Object reference" in prompt_used
    assert "color=red" in prompt_used

    # Assert object primary_image_path was updated in context
    obj_path = context["objects"][0]["primary_image_path"]
    assert obj_path is not None
    assert Path(obj_path).exists()

    # ── Stage 4: generate_videos ──
    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.generate_videos(db_session, job, scenes, context)

    await db_session.refresh(scenes[0])
    assert scenes[0].status == "video_ready"
    assert scenes[0].generated_video_path is not None
    gen_video_mock.assert_called()
    # Video generation received a reference image path
    video_call_kwargs = gen_video_mock.call_args_list[-1].kwargs
    assert video_call_kwargs.get("reference_image_path") is not None

    # ── Cleanup ──
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_objects(db_session, user.id)
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


# ══════════════════════════════════════════════════════════════════════
# T13: Priority-based selection with limited capacity
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_priority_capacity_only_one_selected(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    """T13: 3 objects detected, 1 ref slot → only top-priority selected.

    Simulates IMAGE_TO_VIDEO model (1 ref slot) with 0 characters.
    Planner selects only the Ferrari (critical), leaves Watch + Sunglasses text-only.
    Assert only 1 ObjectRefImage created.
    """
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"priority_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(),
        user_id=user.id,
        status="pending",
        input_data={"prompt": "A thrilling getaway through a neon-lit city"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = PriorityTestPlugin()
    gen_image_mock = _make_gen_image_mock(temp_storage)
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=LLM_RESPONSE_MULTIPLE_OBJECTS)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    # ── enrich_inputs: detects 3 objects (Ferrari, Watch, Sunglasses) ──
    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert len(context.get("objects", [])) == 3
    obj_names = {o["name"] for o in context["objects"]}
    assert obj_names == {"Ferrari", "Watch", "Sunglasses"}

    # Assert all 3 ObjectRef rows exist
    result = await db_session.execute(
        select(ObjectRef).where(ObjectRef.user_id == user.id)
    )
    all_objs = result.scalars().all()
    assert len(all_objs) == 3

    # Assert all 3 JobObjectRef rows exist
    result = await db_session.execute(
        select(JobObjectRef).where(JobObjectRef.job_id == job.id)
    )
    job_objs = result.scalars().all()
    assert len(job_objs) == 3

    # ── plan_scenes: planner selects only Ferrari (highest priority) ──
    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        plan_context = await plugin.plan_scenes(db_session, job, context)

    assert len(plan_context["object_selections"]) == 1
    assert plan_context["object_selections"][0]["object_name"] == "Ferrari"
    context.update(plan_context)

    # ── generate_images: deferred generation runs for Ferrari only ──
    result = await db_session.execute(
        select(VideoScene).where(VideoScene.job_id == job.id)
    )
    scenes = list(result.scalars().all())

    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.generate_images(db_session, job, scenes, context)

    # Assert only 1 ObjectRefImage created (for Ferrari)
    ferrari_obj = next(o for o in all_objs if o.name == "Ferrari")
    result = await db_session.execute(
        select(ObjectRefImage).where(ObjectRefImage.object_ref_id == ferrari_obj.id)
    )
    ferrari_images = result.scalars().all()
    assert len(ferrari_images) == 1

    # Assert no ObjectRefImage for Watch or Sunglasses
    for name in ("Watch", "Sunglasses"):
        obj = next(o for o in all_objs if o.name == name)
        result = await db_session.execute(
            select(ObjectRefImage).where(ObjectRefImage.object_ref_id == obj.id)
        )
        assert len(result.scalars().all()) == 0, f"{name} should have no images"

    # Assert Ferrari has primary_image_path, others do not
    ferrari_ctx = next(o for o in context["objects"] if o["name"] == "Ferrari")
    assert ferrari_ctx["primary_image_path"] is not None

    for name in ("Watch", "Sunglasses"):
        obj_ctx = next(o for o in context["objects"] if o["name"] == name)
        assert obj_ctx["primary_image_path"] is None, f"{name} should stay text-only"

    # ── Cleanup ──
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_objects(db_session, user.id)
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


# ══════════════════════════════════════════════════════════════════════
# T14: Error handling
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_object_error_no_objects_in_llm_response(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    """T14a: LLM returns no objects → pipeline works without object context."""
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"obj_noobj_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(), user_id=user.id, status="pending",
        input_data={"prompt": "A simple driving scene"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = ObjectPipelineTestPlugin()
    gen_image_mock = _make_gen_image_mock(temp_storage)
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=LLM_RESPONSE_CHARS_ONLY)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    # Characters still created
    assert "avatars" in context
    assert len(context["avatars"]) == 1

    # Objects key exists but is empty list
    assert context.get("objects") == []

    # No ObjectRef rows created
    result = await db_session.execute(
        select(ObjectRef).where(ObjectRef.user_id == user.id)
    )
    assert len(result.scalars().all()) == 0

    # Pipeline continues normally
    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        plan_context = await plugin.plan_scenes(db_session, job, context)
        context.update(plan_context)

        result = await db_session.execute(
            select(VideoScene).where(VideoScene.job_id == job.id)
        )
        scenes = list(result.scalars().all())
        assert len(scenes) == 1

        await plugin.generate_images(db_session, job, scenes, context)
        await db_session.refresh(scenes[0])
        assert scenes[0].status == "image_ready"

    # Cleanup
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_object_error_invalid_json_fallback(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    """T14b: LLM returns invalid JSON → pipeline continues with avatars only."""
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"obj_invalid_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(), user_id=user.id, status="pending",
        input_data={"prompt": "A car chase"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = ObjectPipelineTestPlugin()
    gen_image_mock = _make_gen_image_mock(temp_storage)
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=LLM_RESPONSE_NO_JSON)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    # Should not crash — no avatars created (invalid JSON)
    # Pipeline continues
    assert "objects" in context
    assert context["objects"] == []

    # No ObjectRef or Avatar rows created
    result = await db_session.execute(
        select(ObjectRef).where(ObjectRef.user_id == user.id)
    )
    assert len(result.scalars().all()) == 0

    # Pipeline still runs (no avatars = no name, but scenes should still happen)
    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        plan_context = await plugin.plan_scenes(db_session, job, context)
        context.update(plan_context)

        result = await db_session.execute(
            select(VideoScene).where(VideoScene.job_id == job.id)
        )
        scenes = list(result.scalars().all())
        assert len(scenes) == 1

        await plugin.generate_images(db_session, job, scenes, context)
        await db_session.refresh(scenes[0])
        assert scenes[0].status == "image_ready"

    # Cleanup
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_object_error_failed_image_generation_object_text_only(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    """T14c: Object image generation fails → object stays text-only, pipeline continues."""
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"obj_failimg_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(), user_id=user.id, status="pending",
        input_data={"prompt": "A car chase through the Alps"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = ObjectPipelineTestPlugin()
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=LLM_RESPONSE_CHARS_AND_OBJECTS)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    # First call (avatar portrait) succeeds, second call (object ref) fails
    call_count = 0

    async def _flaky_gen_image(*, db, job, prompt, scene_number,
                               title=None, **kwargs):
        nonlocal call_count
        call_count += 1
        # _retry consumes label=, so use prompt to detect object ref calls
        if "Reference image of" in str(prompt):
            raise ValueError("Object reference generation failed")
        fname = f"{title or 'img'}_{scene_number}.png"
        fpath = os.path.join(temp_storage, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4())

    gen_image_mock = AsyncMock(side_effect=_flaky_gen_image)

    # ── enrich_inputs ──
    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert len(context["objects"]) == 1
    assert context["objects"][0]["name"] == "Ferrari"

    # ── plan_scenes ──
    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        plan_context = await plugin.plan_scenes(db_session, job, context)
    context.update(plan_context)

    # ── generate_images: object ref generation will fail ──
    result = await db_session.execute(
        select(VideoScene).where(VideoScene.job_id == job.id)
    )
    scenes = list(result.scalars().all())

    # Reset mock for the generate_images stage
    gen_image_mock = _make_gen_image_mock(temp_storage)

    async def _fail_obj_ref(*, db, job, prompt, scene_number,
                            title=None, **kwargs):
        # _retry consumes label=, so use prompt to detect object ref calls
        if "Reference image of" in str(prompt):
            raise ValueError("Object reference generation failed")
        fname = f"{title or 'img'}_{scene_number}.png"
        fpath = os.path.join(temp_storage, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4())

    gen_image_mock = AsyncMock(side_effect=_fail_obj_ref)

    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.generate_images(db_session, job, scenes, context)

    # Scene still completed successfully
    await db_session.refresh(scenes[0])
    assert scenes[0].status == "image_ready"

    # Object stayed text-only (no primary_image_path)
    assert context["objects"][0]["primary_image_path"] is None

    # No ObjectRefImage created
    result = await db_session.execute(
        select(ObjectRef).where(ObjectRef.user_id == user.id)
    )
    obj_refs = result.scalars().all()
    assert len(obj_refs) == 1
    result = await db_session.execute(
        select(ObjectRefImage).where(ObjectRefImage.object_ref_id == obj_refs[0].id)
    )
    assert len(result.scalars().all()) == 0

    # Cleanup
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_objects(db_session, user.id)
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_object_error_all_object_images_fail_pipeline_completes(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    """T14d: All object image generations fail → pipeline completes with text-only objects."""
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"obj_allfail_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(), user_id=user.id, status="pending",
        input_data={"prompt": "A heist in Monaco"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = ObjectPipelineTestPlugin()
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=LLM_RESPONSE_CHARS_AND_OBJECTS)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    # ── enrich_inputs ──
    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, _make_gen_image_mock(temp_storage)),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert len(context["objects"]) == 1

    # ── plan_scenes ──
    with (
        patch(PATCH_GEN_IMAGE, AsyncMock()),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        plan_context = await plugin.plan_scenes(db_session, job, context)
    context.update(plan_context)

    # ── generate_images: ALL object ref calls fail ──
    result = await db_session.execute(
        select(VideoScene).where(VideoScene.job_id == job.id)
    )
    scenes = list(result.scalars().all())

    async def _always_fail_obj_ref(*, db, job, prompt, scene_number,
                                   title=None, **kwargs):
        # _retry consumes label=, so use prompt to detect object ref calls
        if "Reference image of" in str(prompt):
            raise RuntimeError("Provider overloaded — retries exhausted")
        fname = f"{title or 'img'}_{scene_number}.png"
        fpath = os.path.join(temp_storage, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4())

    gen_image_mock = AsyncMock(side_effect=_always_fail_obj_ref)

    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.generate_images(db_session, job, scenes, context)

    # Pipeline still completes normally
    await db_session.refresh(scenes[0])
    assert scenes[0].status == "image_ready"

    # Object is text-only
    assert context["objects"][0]["primary_image_path"] is None

    # No ObjectRefImage created
    result = await db_session.execute(
        select(ObjectRef).where(ObjectRef.user_id == user.id)
    )
    obj_refs = result.scalars().all()
    result = await db_session.execute(
        select(ObjectRefImage).where(ObjectRefImage.object_ref_id == obj_refs[0].id)
    )
    assert len(result.scalars().all()) == 0

    # Cleanup
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_objects(db_session, user.id)
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_object_error_missing_visual_properties_handled(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    """T14e: Object has no visual_properties field → handled gracefully (no injection)."""
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"obj_noviz_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(), user_id=user.id, status="pending",
        input_data={"prompt": "A detective's investigation"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = ObjectPipelineTestPlugin()
    gen_image_mock = _make_gen_image_mock(temp_storage)
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=LLM_RESPONSE_OBJECT_NO_VISUAL_PROPS)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    # ── enrich_inputs ──
    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert len(context["objects"]) == 1
    assert context["objects"][0]["name"] == "Notebook"
    assert context["objects"][0]["visual_properties"] is None or \
        context["objects"][0]["visual_properties"] == {}

    # ObjectRef persisted with null visual_properties
    result = await db_session.execute(
        select(ObjectRef).where(ObjectRef.user_id == user.id)
    )
    obj_refs = result.scalars().all()
    assert len(obj_refs) == 1
    assert obj_refs[0].visual_properties is None or obj_refs[0].visual_properties == {}

    # ── plan_scenes ──
    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        plan_context = await plugin.plan_scenes(db_session, job, context)
    context.update(plan_context)

    # ── generate_images ──
    result = await db_session.execute(
        select(VideoScene).where(VideoScene.job_id == job.id)
    )
    scenes = list(result.scalars().all())

    gen_image_mock = _make_gen_image_mock(temp_storage)

    async def _gen_capture(*, db, job, prompt, scene_number,
                           title=None, **kwargs):
        fname = f"{title or 'img'}_{scene_number}.png"
        fpath = os.path.join(temp_storage, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4())

    gen_image_mock = AsyncMock(side_effect=_gen_capture)

    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.generate_images(db_session, job, scenes, context)

    await db_session.refresh(scenes[0])
    assert scenes[0].status == "image_ready"

    # Scene image prompt should NOT have Object reference injection
    # (because visual_properties is empty/None)
    scene_prompt_calls = [
        c.kwargs.get("prompt", "") for c in gen_image_mock.call_args_list
    ]
    scene_prompts = [p for p in scene_prompt_calls if "Object reference" in p]
    assert len(scene_prompts) == 0, (
        "Scene prompt should not have Object reference injection when "
        "visual_properties is empty"
    )

    # ObjectRefImage was created for the notebook
    result = await db_session.execute(
        select(ObjectRefImage).where(ObjectRefImage.object_ref_id == obj_refs[0].id)
    )
    assert len(result.scalars().all()) == 1

    # Cleanup
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_objects(db_session, user.id)
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()
