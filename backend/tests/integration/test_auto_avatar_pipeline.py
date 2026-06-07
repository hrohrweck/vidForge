"""Integration tests for the auto-avatar pipeline: end-to-end flow from job
creation through all pipeline stages with auto-generated characters.

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/test_auto_avatar_pipeline.py -v
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Avatar, AvatarImage, Job, User, VideoScene
from app.plugins.base import PluginBase

pytestmark = pytest.mark.integration


class AutoAvatarTestPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "auto_avatar_test"

    @property
    def display_name(self) -> str:
        return "Auto Avatar Pipeline Test"

    @property
    def description(self) -> str:
        return "Test plugin for auto-avatar pipeline integration tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        avatars = context.get("avatars", [])
        avatar_name = avatars[0]["name"] if avatars else "Unknown"
        scene = VideoScene(
            id=uuid4(),
            job_id=job.id,
            scene_number=1,
            start_time=0.0,
            end_time=5.0,
            visual_description=f"Close-up of {avatar_name} walking through a noir alley",
            image_prompt=f"Film still of {avatar_name} in a noir alley, cinematic lighting",
            status="pending",
        )
        db.add(scene)
        await db.commit()
        return {"scene_count": 1}


VALID_LLM_RESPONSE = (
    '{"characters": ['
    '{"name": "Scarlett", "gender": "female", '
    '"bio": "A weary detective in 1940s Chicago with a sharp mind and a drinking problem.", '
    '"role": "Lead detective"}]}'
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
    async def _gen(*, db, job, prompt, scene_number, model_preference=None,
                    aspect_ratio="3:2", title=None, reference_image_path=None,
                    reference_image_strength=0.75, lora_path=None,
                    lora_strength=0.8, provider_id=None, **kwargs):
        fname = f"{title or 'avatar'}_{scene_number}.png"
        fpath = os.path.join(tmp_dir, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4())
    return AsyncMock(side_effect=_gen)


def _make_gen_video_mock(tmp_dir):
    async def _gen(*, db, job, prompt, scene_number, reference_image_path=None,
                    provider_id=None, model_preference=None, duration=5,
                    aspect_ratio="16:9", title=None, **kwargs):
        fname = f"video_s{scene_number}.mp4"
        fpath = os.path.join(tmp_dir, fname)
        Path(fpath).write_bytes(
            b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41"
            b"\x00\x00\x00\x08free" + b"\x00" * 500
        )
        return (fname, "test-video-model", uuid4(), 5.0, None)
    return AsyncMock(side_effect=_gen)


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


async def _cleanup_avatars(db_session, user_id):
    from sqlalchemy import delete as sa_delete, update as sa_update
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


@pytest.mark.asyncio
async def test_e2e_auto_avatar_pipeline_full(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"auto_avatar_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(),
        user_id=user.id,
        status="pending",
        input_data={"prompt": "A noir detective story in 1940s Chicago"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = AutoAvatarTestPlugin()
    gen_image_mock = _make_gen_image_mock(temp_storage)
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert "avatars" in context
    assert len(context["avatars"]) == 1
    assert context["avatars"][0]["name"] == "Scarlett"
    assert context["avatars"][0]["primary_image_path"] is not None

    result = await db_session.execute(
        select(Avatar).where(Avatar.user_id == user.id)
    )
    avatars = result.scalars().all()
    assert len(avatars) == 1
    assert avatars[0].name == "Scarlett"

    result = await db_session.execute(
        select(AvatarImage).where(AvatarImage.avatar_id == avatars[0].id)
    )
    images = result.scalars().all()
    assert len(images) == 1
    assert images[0].is_primary is True

    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.plan_scenes(db_session, job, context)

        result = await db_session.execute(
            select(VideoScene).where(VideoScene.job_id == job.id)
        )
        scenes = list(result.scalars().all())
        assert len(scenes) == 1
        scene = scenes[0]
        assert "Scarlett" in (scene.visual_description or "")
        assert "Scarlett" in (scene.image_prompt or "")

        await plugin.generate_images(db_session, job, scenes, context)
        await db_session.refresh(scene)
        assert scene.status == "image_ready"
        assert scene.reference_image_path is not None
        gen_image_mock.assert_called()
        assert gen_image_mock.call_args.kwargs.get("reference_image_path") is not None

        await plugin.generate_videos(db_session, job, scenes, context)
        await db_session.refresh(scene)
        assert scene.status == "video_ready"
        assert scene.generated_video_path is not None
        gen_video_mock.assert_called()
        assert gen_video_mock.call_args.kwargs.get("reference_image_path") is not None

    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_e2e_auto_avatar_pipeline_fallback(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"fallback_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(),
        user_id=user.id,
        status="pending",
        input_data={"prompt": "A noir detective story"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = AutoAvatarTestPlugin()
    gen_image_mock = _make_gen_image_mock(temp_storage)
    gen_video_mock = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value="Not valid JSON, just some text about characters")
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert "avatars" not in context or len(context.get("avatars", [])) == 0

    with (
        patch(PATCH_GEN_IMAGE, gen_image_mock),
        patch(PATCH_GEN_VIDEO, gen_video_mock),
        patch(PATCH_PREFS, prefs_mock),
    ):
        await plugin.plan_scenes(db_session, job, context)
        result = await db_session.execute(
            select(VideoScene).where(VideoScene.job_id == job.id)
        )
        scenes = list(result.scalars().all())
        assert len(scenes) == 1

        await plugin.generate_images(db_session, job, scenes, context)
        await db_session.refresh(scenes[0])
        assert scenes[0].status == "image_ready"
        gen_image_mock.assert_called()
        assert gen_image_mock.call_args.kwargs.get("reference_image_path") is None

        await plugin.generate_videos(db_session, job, scenes, context)
        await db_session.refresh(scenes[0])
        assert scenes[0].status == "video_ready"

    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()
