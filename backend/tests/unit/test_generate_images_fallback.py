"""Unit tests for img2img → T2I fallback in PluginBase.generate_images().

Tests cover:
- img2img fails (retries exhausted) → T2I fallback succeeds
- img2img fails → T2I fallback also fails → scene marked failed
- T2I-only path (no reference image) → no fallback triggered
- Auto-avatar creation: image gen fails → avatar still persisted
"""

import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import Avatar, AvatarImage, Job, VideoScene
from app.plugins.base import PluginBase

# ── Test plugin ────────────────────────────────────────────────────────────


class TestFallbackPlugin(PluginBase):
    """Minimal plugin for testing generate_images fallback behaviour."""

    @property
    def plugin_id(self) -> str:
        return "test_fallback"

    @property
    def display_name(self) -> str:
        return "Test Fallback Plugin"

    @property
    def description(self) -> str:
        return "Test plugin for generate_images fallback unit tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        return {"scene_count": 1}


# ── Patch targets ──────────────────────────────────────────────────────────

PATCH_GEN_IMAGE = "app.services.media_generator.generate_image"
PATCH_PREFS = "app.api.models.get_default_model_preferences"
PATCH_LOGGER = "app.plugins.base.logger"
PATCH_IMPORT = "app.plugins.base._import_scene_asset"

# ── Helpers ────────────────────────────────────────────────────────────────


def make_job(user_id, extra_input=None):
    input_data = {"prompt": "A sci-fi adventure"}
    if extra_input:
        input_data.update(extra_input)
    return Job(
        id=uuid4(),
        user_id=user_id,
        status="images_ready",
        input_data=input_data,
    )


def make_scene(job_id, scene_number=1, image_prompt="A cinematic shot", start_time=0, end_time=5):
    return VideoScene(
        id=uuid4(),
        job_id=job_id,
        scene_number=scene_number,
        start_time=start_time,
        end_time=end_time,
        image_prompt=image_prompt,
        status="pending",
    )


class NonRecoverableError(Exception):
    """Error that does NOT match _RECOVERABLE_MARKERS — causes _retry to raise immediately."""


def _make_gen_image_success(storage_dir):
    """Return an AsyncMock that writes a real file and returns a success tuple."""

    async def _gen(*, db, job, prompt, scene_number, model_preference,
                    aspect_ratio="3:2", title=None, **kwargs):
        fname = f"scene_{scene_number}.png"
        fpath = os.path.join(storage_dir, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4(), Decimal("0"))

    return AsyncMock(side_effect=_gen)


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory and patch settings.storage_path."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.storage_path = tmp
            yield tmp


# ── Tests ──────────────────────────────────────────────────────────────────


class TestGenerateImagesFallback:

    @pytest.mark.asyncio
    async def test_img2img_fails_t2i_succeeds(
        self, db_session, regular_user, temp_storage
    ):
        """img2img fails (non-recoverable error) → T2I fallback succeeds → scene image_ready."""
        job = make_job(regular_user.id)
        scene = make_scene(job.id, scene_number=1, image_prompt="A space station")
        db_session.add(job)
        db_session.add(scene)
        await db_session.commit()

        # Avatar context with a valid primary_image_path
        avatar_fake_path = os.path.join(temp_storage, "avatar_ref.png")
        Path(avatar_fake_path).write_bytes(b"fake-avatar-png")

        context = {"avatars": [{"primary_image_path": avatar_fake_path}]}

        # Call 1 (img2img): non-recoverable error → _retry re-raises immediately
        # Call 2 (T2I fallback): success tuple
        t2i_image_path = os.path.join(temp_storage, "scene_fallback.png")
        Path(t2i_image_path).write_bytes(b"fake-png-t2i")

        gen_image_mock = AsyncMock(side_effect=[
            NonRecoverableError("GPU out of memory"),
            ("scene_fallback.png", "test-model", uuid4(), Decimal("0")),
        ])
        import_mock = AsyncMock(return_value=None)

        with (
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_IMPORT, import_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            plugin = TestFallbackPlugin()
            await plugin.generate_images(db_session, job, [scene], context)

        # Verify the scene got an image path and is marked ready
        assert scene.status == "image_ready"
        assert scene.reference_image_path is not None
        assert scene.error_message is None

        # Verify generate_image was called twice: once with ref, once without
        assert gen_image_mock.call_count == 2
        call_1 = gen_image_mock.call_args_list[0]
        call_2 = gen_image_mock.call_args_list[1]
        assert "reference_image_path" in call_1.kwargs
        assert call_1.kwargs["reference_image_path"] == avatar_fake_path
        assert "reference_image_path" not in call_2.kwargs

        # Verify fallback warning was logged
        log_mock.warning.assert_called()

    @pytest.mark.asyncio
    async def test_img2img_fails_t2i_also_fails(
        self, db_session, regular_user, temp_storage
    ):
        """img2img fails → T2I fallback also fails → scene marked failed."""
        job = make_job(regular_user.id)
        scene = make_scene(job.id, scene_number=1, image_prompt="A space station")
        db_session.add(job)
        db_session.add(scene)
        await db_session.commit()

        avatar_fake_path = os.path.join(temp_storage, "avatar_ref.png")
        Path(avatar_fake_path).write_bytes(b"fake-avatar-png")

        context = {"avatars": [{"primary_image_path": avatar_fake_path}]}

        # Both calls fail with non-recoverable errors
        gen_image_mock = AsyncMock(side_effect=[
            NonRecoverableError("GPU out of memory"),
            NonRecoverableError("All models busy"),
        ])
        import_mock = AsyncMock(return_value=None)

        with (
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_IMPORT, import_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            plugin = TestFallbackPlugin()
            await plugin.generate_images(db_session, job, [scene], context)

        # Scene should be marked failed
        assert scene.status == "failed"
        assert scene.error_message is not None
        assert "GPU out of memory" in scene.error_message

        # Both calls happened
        assert gen_image_mock.call_count == 2

        # Verify both warning and error were logged
        log_mock.warning.assert_called()  # img2img fallback warning
        log_mock.error.assert_called()    # T2I fallback failure + final error

    @pytest.mark.asyncio
    async def test_t2i_only_no_avatar_ref_no_fallback_triggered(
        self, db_session, regular_user, temp_storage
    ):
        """When no avatar reference exists, a T2I failure does NOT trigger fallback."""
        job = make_job(regular_user.id)
        scene = make_scene(job.id, scene_number=1, image_prompt="A space station")
        db_session.add(job)
        db_session.add(scene)
        await db_session.commit()

        # No avatar reference — pure T2I by default
        context = {"avatars": []}

        gen_image_mock = AsyncMock(side_effect=[
            NonRecoverableError("GPU out of memory"),
        ])
        import_mock = AsyncMock(return_value=None)

        with (
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_IMPORT, import_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            plugin = TestFallbackPlugin()
            await plugin.generate_images(db_session, job, [scene], context)

        # Should fail immediately — no fallback since no avatar_ref_path
        assert scene.status == "failed"
        assert scene.error_message is not None

        # Only one call (no T2I fallback)
        assert gen_image_mock.call_count == 1

        # No fallback warning (avatar_ref_path was None)
        fallback_warnings = [
            c for c in log_mock.warning.call_args_list
            if "falling back to T2I" in str(c)
        ]
        assert len(fallback_warnings) == 0

    @pytest.mark.asyncio
    async def test_t2i_success_no_reference(
        self, db_session, regular_user, temp_storage
    ):
        """T2I-only path (no reference image) succeeds normally without fallback."""
        job = make_job(regular_user.id)
        scene = make_scene(job.id, scene_number=1, image_prompt="A sunset over mountains")
        db_session.add(job)
        db_session.add(scene)
        await db_session.commit()

        context = {"avatars": []}

        gen_image_mock = _make_gen_image_success(temp_storage)
        import_mock = AsyncMock(return_value=None)

        with (
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_IMPORT, import_mock),
        ):
            plugin = TestFallbackPlugin()
            await plugin.generate_images(db_session, job, [scene], context)

        assert scene.status == "image_ready"
        assert scene.reference_image_path is not None
        assert gen_image_mock.call_count == 1


class TestAutoAvatarFallback:

    PATCH_LLM = "app.services.llm_service.LLMClient"
    VALID_LLM = (
        '{"characters": [{"name": "Zara", "gender": "female", '
        '"bio": "A pilot.", "role": "Protagonist"}]}'
    )

    @pytest.mark.asyncio
    async def test_image_gen_fails_avatar_still_created(
        self, db_session, regular_user, temp_storage
    ):
        """Auto-avatar image generation fails → avatar persisted without image."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestFallbackPlugin()

        llm_mock = AsyncMock(return_value=self.VALID_LLM)
        gen_image_mock = AsyncMock(side_effect=NonRecoverableError("GPU OOM"))
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(self.PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        # Avatar should still be in context with None image path
        assert len(ctx["avatars"]) == 1
        assert ctx["avatars"][0]["name"] == "Zara"
        assert ctx["avatars"][0]["primary_image_path"] is None

        # Avatar record should exist in DB
        result = await db_session.execute(
            select(Avatar).where(Avatar.user_id == regular_user.id)
        )
        avatars = result.scalars().all()
        assert len(avatars) == 1
        assert avatars[0].name == "Zara"

        # No AvatarImage records (gen failed)
        result = await db_session.execute(
            select(AvatarImage).join(
                Avatar, AvatarImage.avatar_id == Avatar.id
            ).where(Avatar.user_id == regular_user.id)
        )
        images = result.scalars().all()
        assert len(images) == 0

        # Warning should mention "text-only"
        warnings = [
            c for c in log_mock.warning.call_args_list
            if "text-only" in str(c)
        ]
        assert len(warnings) >= 1
