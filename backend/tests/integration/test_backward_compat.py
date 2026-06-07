"""Backward compatibility tests: legacy jobs without avatars field proceed normally.

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/test_backward_compat.py -v
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


class BackwardCompatPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "backward_compat_test"

    @property
    def display_name(self) -> str:
        return "Backward Compat Test"

    @property
    def description(self) -> str:
        return "Test plugin for backward compatibility"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        scene = VideoScene(
            id=uuid4(),
            job_id=job.id,
            scene_number=1,
            start_time=0.0,
            end_time=4.0,
            visual_description="A serene landscape with mountains",
            image_prompt="Panoramic mountain vista at golden hour, 4K cinematic",
            status="pending",
        )
        db.add(scene)
        await db.commit()
        return {"scene_count": 1}


VALID_LLM_RESPONSE = (
    '{"characters": ['
    '{"name": "Elena", "gender": "female", '
    '"bio": "A hiker exploring mountain trails.", '
    '"role": "Protagonist"}]}'
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
        fname = f"{title or 'img'}_{scene_number}.png"
        fpath = os.path.join(tmp_dir, fname)
        Path(fpath).write_bytes(b"png-data")
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
        return (fname, "test-video-model", uuid4(), 4.0, None)
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
async def test_job_without_avatars_field_completes_pipeline(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"bwcompat1_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(),
        user_id=user.id,
        status="pending",
        input_data={"prompt": "A mountain adventure story"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = BackwardCompatPlugin()
    gen_img = _make_gen_image_mock(temp_storage)
    gen_vid = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_img),
        patch(PATCH_GEN_VIDEO, gen_vid),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert "avatars" in context
    assert len(context["avatars"]) >= 1

    with (
        patch(PATCH_GEN_IMAGE, gen_img),
        patch(PATCH_GEN_VIDEO, gen_vid),
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

        await plugin.generate_videos(db_session, job, scenes, context)
        await db_session.refresh(scenes[0])
        assert scenes[0].status == "video_ready"

    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_job_missing_avatars_key_no_keyerror(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"bwcompat2_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(),
        user_id=user.id,
        status="pending",
        input_data={"prompt": "A sci-fi story"},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = BackwardCompatPlugin()
    gen_img = _make_gen_image_mock(temp_storage)
    llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_img),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})

    assert "avatars" in context
    assert len(context["avatars"]) == 1
    assert context["avatars"][0]["name"] == "Elena"

    result = await db_session.execute(
        select(Avatar).where(Avatar.user_id == user.id)
    )
    avatars = result.scalars().all()
    assert len(avatars) == 1

    from sqlalchemy import delete as sa_delete
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_job_empty_avatars_list_fallback_t2i(
    db_session: AsyncSession, temp_storage: str, no_sleep: AsyncMock,
):
    test_id = str(uuid4())[:8]
    user = _make_test_user(f"bwcompat3_{test_id}@test.com")
    db_session.add(user)
    await db_session.commit()

    job = Job(
        id=uuid4(),
        user_id=user.id,
        status="pending",
        input_data={"prompt": "A fantasy adventure", "avatars": []},
    )
    db_session.add(job)
    await db_session.commit()

    plugin = BackwardCompatPlugin()
    gen_img = _make_gen_image_mock(temp_storage)
    gen_vid = _make_gen_video_mock(temp_storage)
    llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
    prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

    with (
        patch(PATCH_LLM) as llm_cls,
        patch(PATCH_GEN_IMAGE, gen_img),
        patch(PATCH_GEN_VIDEO, gen_vid),
        patch(PATCH_PREFS, prefs_mock),
    ):
        llm_cls.return_value.generate = llm_mock
        context = await plugin.enrich_inputs(db_session, job, {})
        assert "avatars" in context
        assert len(context["avatars"]) == 1

        await plugin.plan_scenes(db_session, job, context)

        result = await db_session.execute(
            select(VideoScene).where(VideoScene.job_id == job.id)
        )
        scenes = list(result.scalars().all())
        assert len(scenes) == 1

        await plugin.generate_images(db_session, job, scenes, context)
        await db_session.refresh(scenes[0])
        assert scenes[0].status == "image_ready"

        await plugin.generate_videos(db_session, job, scenes, context)
        await db_session.refresh(scenes[0])
        assert scenes[0].status == "video_ready"

    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.job_id == job.id))
    await db_session.execute(sa_delete(Job).where(Job.id == job.id))
    await _cleanup_avatars(db_session, user.id)
    await db_session.execute(sa_delete(User).where(User.id == user.id))
    await db_session.commit()
