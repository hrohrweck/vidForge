"""Unit tests for avatar reference propagation through video sub-clip chaining.

Tests cover:
- Short scene (≤5s): reference_image_path passed to generate_video
- Long scene (>5s): reference_image_path flows to first sub-clip
- Subsequent sub-clips use ~80% frame of previous clip as seed
- Avatar context included in sub-scene prompt generation
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, VideoScene
from app.plugins.base import PluginBase

# Patch targets matching the local imports in base.py
PATCH_GEN_VIDEO = "app.services.media_generator.generate_video"
PATCH_VIDEO_PROCESSOR = "app.services.video_processor.VideoProcessor"
PATCH_LOGGER = "app.plugins.base.logger"
PATCH_MEDIA_SETTINGS = "app.services.media_generator.settings"


# ── Test Plugin ────────────────────────────────────────────────────────────

class TestVideoChainPlugin(PluginBase):
    """Minimal plugin for testing video sub-clip chaining behaviour."""

    @property
    def plugin_id(self) -> str:
        return "test_video_chain"

    @property
    def display_name(self) -> str:
        return "Test Video Chain"

    @property
    def description(self) -> str:
        return "Test plugin for video sub-clip chaining unit tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        return {"scene_count": 1}


# ── Helpers ────────────────────────────────────────────────────────────────


def make_job(user_id, extra_input=None):
    input_data = {"prompt": "A cinematic adventure", "aspect_ratio": "16:9"}
    if extra_input:
        input_data.update(extra_input)
    return Job(
        id=uuid4(),
        user_id=user_id,
        status="pending",
        input_data=input_data,
    )


def _make_video_mock(tmp_dir):
    """Return an AsyncMock that writes a fake video file and returns a tuple."""

    async def _gen_video(*, db, job, prompt, scene_number,
                         reference_image_path=None,
                         provider_id=None, model_preference=None,
                         duration=5, aspect_ratio="16:9", title=None,
                         **kwargs):
        from app.services.media_generator import get_scene_output_dir

        out_dir = get_scene_output_dir(str(job.id), scene_number)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"sub_{scene_number:03d}.mp4"
        fpath = out_dir / fname
        fpath.write_bytes(b"fake-mp4-data")

        rel_path = str(fpath.relative_to(tmp_dir))
        return (rel_path, "test-video-model", uuid4(), float(duration), None)

    return AsyncMock(side_effect=_gen_video)


def _make_video_mock_safe():
    """Return an AsyncMock that returns a safe tuple without relative-path computation.

    The return value from generate_video is stored as scene.generated_video_path
    but our tests only assert on the reference_image_path argument.
    """

    async def _gen_video(*, db, job, prompt, scene_number,
                         reference_image_path=None,
                         provider_id=None, model_preference=None,
                         duration=5, aspect_ratio="16:9", title=None,
                         **kwargs):
        return ("output/test/scene_video.mp4", "test-model",
                uuid4(), float(duration), None)

    return AsyncMock(side_effect=_gen_video)


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory and patch all settings paths."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.storage_path = tmp
            # Also patch the cached module-level settings in media_generator
            with patch("app.services.media_generator.settings") as media_settings:
                media_settings.storage_path = tmp
                yield tmp


def _scene(scene_number: int, start: float = 0.0, end: float = 5.0,
           image_prompt: str = "A sunny day",
           visual_description: str = "",
           reference_image_path: str | None = None) -> VideoScene:
    """Create a minimal VideoScene for generate_videos tests."""
    return VideoScene(
        id=uuid4(),
        job_id=uuid4(),
        scene_number=scene_number,
        start_time=start,
        end_time=end,
        image_prompt=image_prompt,
        visual_description=visual_description or image_prompt,
        reference_image_path=reference_image_path,
        status="pending",
    )


# ── Tests ──────────────────────────────────────────────────────────────────


class TestVideoChainingAvatarShortScene:
    """Short scene (≤5s): reference_image_path passed directly."""

    @pytest.mark.asyncio
    async def test_short_scene_passes_reference_image(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        avatar_ref = str(Path(temp_storage) / "avatar_ref.png")
        Path(avatar_ref).write_bytes(b"fake-avatar-png")

        scene = _scene(
            1, start=0.0, end=5.0,
            image_prompt="A hero walks into the sunset",
            reference_image_path=avatar_ref,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        captured_kwargs: list[dict] = []

        async def _capture_video(**kwargs):
            captured_kwargs.append(kwargs)
            from app.services.media_generator import get_scene_output_dir

            out_dir = get_scene_output_dir(str(job.id), 1)
            out_dir.mkdir(parents=True, exist_ok=True)
            fpath = out_dir / "scene_video.mp4"
            fpath.write_bytes(b"fake-mp4-data")
            return (str(fpath.relative_to(temp_storage)),
                    "test-model", uuid4(), 5.0, None)

        gen_video_mock = AsyncMock(side_effect=_capture_video)

        plugin = TestVideoChainPlugin()

        with patch(PATCH_GEN_VIDEO, gen_video_mock):
            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={},
            )

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["reference_image_path"] == avatar_ref

    @pytest.mark.asyncio
    async def test_short_scene_null_reference_image_still_works(
        self, db_session, regular_user, temp_storage
    ):
        """Scene without reference_image_path should work (text-to-video fallback)."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        scene = _scene(
            1, start=0.0, end=5.0,
            image_prompt="Abstract patterns emerge",
            reference_image_path=None,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        captured_kwargs: list[dict] = []

        async def _capture_video(**kwargs):
            captured_kwargs.append(kwargs)
            from app.services.media_generator import get_scene_output_dir

            out_dir = get_scene_output_dir(str(job.id), 1)
            out_dir.mkdir(parents=True, exist_ok=True)
            fpath = out_dir / "scene_video.mp4"
            fpath.write_bytes(b"fake-mp4-data")
            return (str(fpath.relative_to(temp_storage)),
                    "test-model", uuid4(), 5.0, None)

        gen_video_mock = AsyncMock(side_effect=_capture_video)

        plugin = TestVideoChainPlugin()

        with patch(PATCH_GEN_VIDEO, gen_video_mock):
            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={},
            )

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["reference_image_path"] is None


class TestVideoChainingAvatarLongScene:
    """Long scene (>5s): sub-clip chaining with reference image propagation."""

    @staticmethod
    def _make_capturing_video_mock(call_log: list):
        """Return an AsyncMock that logs all kwargs and returns a safe tuple."""

        async def _capture(**kwargs):
            call_log.append(kwargs)
            return ("output/test/scene_video.mp4", "test-model",
                    uuid4(), float(kwargs.get("duration", 5)), None)

        return AsyncMock(side_effect=_capture)

    @pytest.mark.asyncio
    async def test_first_subclip_uses_scene_reference_image(
        self, db_session, regular_user, temp_storage
    ):
        """10s scene → 2 sub-clips. First sub-clip gets scene.reference_image_path."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        avatar_ref = str(Path(temp_storage) / "avatar_ref.png")
        Path(avatar_ref).write_bytes(b"fake-avatar-png")

        scene = _scene(
            1, start=0.0, end=10.0,
            image_prompt="A hero battles a dragon",
            reference_image_path=avatar_ref,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        gen_video_calls: list[dict] = []
        gen_video_mock = self._make_capturing_video_mock(gen_video_calls)

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        async def _fake_sub_prompts(db, job, scene, num_clips, avatars=None):
            return [
                "The hero charges at the dragon, sword raised",
                "The dragon breathes fire, the hero dodges",
            ]

        plugin = TestVideoChainPlugin()
        plugin._generate_sub_scene_prompts = AsyncMock(
            side_effect=_fake_sub_prompts
        )

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
        ):
            vp_mock.extract_frame = extract_mock
            vp_mock.merge_with_crossfade = AsyncMock()
            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={},
            )

        assert len(gen_video_calls) == 2
        assert gen_video_calls[0]["reference_image_path"] == avatar_ref
        assert gen_video_calls[1]["reference_image_path"] is not None
        assert gen_video_calls[1]["reference_image_path"] != avatar_ref
        assert "seed_sub_1" in gen_video_calls[1]["reference_image_path"]

    @pytest.mark.asyncio
    async def test_three_subclip_chain_seed_propagation(
        self, db_session, regular_user, temp_storage
    ):
        """15s scene → 3 sub-clips. Verify seed chain: ref → frame1 → frame2."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        avatar_ref = str(Path(temp_storage) / "avatar_ref.png")
        Path(avatar_ref).write_bytes(b"fake-avatar-png")

        scene = _scene(
            1, start=0.0, end=15.0,
            image_prompt="An epic space battle",
            reference_image_path=avatar_ref,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        gen_video_calls: list[dict] = []
        gen_video_mock = self._make_capturing_video_mock(gen_video_calls)

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        async def _fake_sub_prompts(db, job, scene, num_clips, avatars=None):
            return [f"Space battle part {i + 1}" for i in range(num_clips)]

        plugin = TestVideoChainPlugin()
        plugin._generate_sub_scene_prompts = AsyncMock(
            side_effect=_fake_sub_prompts
        )

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
        ):
            vp_mock.extract_frame = extract_mock
            vp_mock.merge_with_crossfade = AsyncMock()
            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={},
            )

        assert len(gen_video_calls) == 3
        assert gen_video_calls[0]["reference_image_path"] == avatar_ref
        assert gen_video_calls[1]["reference_image_path"] != avatar_ref
        assert "seed_sub_1" in gen_video_calls[1]["reference_image_path"]
        assert gen_video_calls[2]["reference_image_path"] != avatar_ref
        assert "seed_sub_2" in gen_video_calls[2]["reference_image_path"]
        assert (gen_video_calls[1]["reference_image_path"] !=
                gen_video_calls[2]["reference_image_path"])

    @pytest.mark.asyncio
    async def test_long_scene_null_reference_image_propagates_none(
        self, db_session, regular_user, temp_storage
    ):
        """10s scene without reference_image_path — first sub-clip gets None."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        scene = _scene(
            1, start=0.0, end=10.0,
            image_prompt="Abstract visuals evolve",
            reference_image_path=None,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        gen_video_calls: list[dict] = []
        gen_video_mock = self._make_capturing_video_mock(gen_video_calls)

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        async def _fake_sub_prompts(db, job, scene, num_clips, avatars=None):
            return [f"Abstract part {i + 1}" for i in range(num_clips)]

        plugin = TestVideoChainPlugin()
        plugin._generate_sub_scene_prompts = AsyncMock(
            side_effect=_fake_sub_prompts
        )

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
        ):
            vp_mock.extract_frame = extract_mock
            vp_mock.merge_with_crossfade = AsyncMock()
            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={},
            )

        assert len(gen_video_calls) == 2
        assert gen_video_calls[0]["reference_image_path"] is None
        assert gen_video_calls[1]["reference_image_path"] is not None


class TestVideoChainingAvatarPromptContext:
    """Avatar context flows into sub-scene prompt generation."""

    @pytest.mark.asyncio
    async def test_avatars_in_context_passed_to_sub_prompt_generator(
        self, db_session, regular_user, temp_storage
    ):
        """When avatars exist in context, they are passed to _generate_sub_scene_prompts."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        avatar_ref = str(Path(temp_storage) / "alice_ref.png")
        Path(avatar_ref).write_bytes(b"fake-avatar-png")

        scene = _scene(
            1, start=0.0, end=10.0,
            image_prompt="Alice investigates the crime scene",
            reference_image_path=avatar_ref,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        avatar_context = [
            {
                "id": str(uuid4()),
                "name": "Alice",
                "gender": "female",
                "bio": "A sharp detective with keen instincts",
                "role": "Lead investigator",
                "primary_image_path": avatar_ref,
                "consistency_strategy": "character_sheet",
                "deleted": False,
            }
        ]

        gen_video_mock = _make_video_mock(temp_storage)

        captured_prompt_avatars = []

        async def _capture_sub_prompts(db, job, scene, num_clips, avatars=None):
            captured_prompt_avatars.append(avatars)
            return [f"Part {i + 1}" for i in range(num_clips)]

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        plugin = TestVideoChainPlugin()
        plugin._generate_sub_scene_prompts = AsyncMock(
            side_effect=_capture_sub_prompts
        )

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
        ):
            vp_mock.extract_frame = extract_mock
            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={"avatars": avatar_context},
            )

        assert len(captured_prompt_avatars) == 1
        assert captured_prompt_avatars[0] is not None
        assert len(captured_prompt_avatars[0]) == 1
        assert captured_prompt_avatars[0][0]["name"] == "Alice"
        assert captured_prompt_avatars[0][0]["bio"] == \
            "A sharp detective with keen instincts"

    @pytest.mark.asyncio
    async def test_no_avatars_in_context_passes_none_to_prompt_generator(
        self, db_session, regular_user, temp_storage
    ):
        """When no avatars in context, None is passed to _generate_sub_scene_prompts."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        scene = _scene(
            1, start=0.0, end=10.0,
            image_prompt="A beautiful sunset over the ocean",
            reference_image_path=None,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        gen_video_mock = _make_video_mock(temp_storage)

        captured_prompt_avatars = []

        async def _capture_sub_prompts(db, job, scene, num_clips, avatars=None):
            captured_prompt_avatars.append(avatars)
            return [f"Part {i + 1}" for i in range(num_clips)]

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        plugin = TestVideoChainPlugin()
        plugin._generate_sub_scene_prompts = AsyncMock(
            side_effect=_capture_sub_prompts
        )

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
        ):
            vp_mock.extract_frame = extract_mock
            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={},
            )

        assert len(captured_prompt_avatars) == 1
        # Empty context → avatars == [] which is falsy but not None
        assert captured_prompt_avatars[0] == [] or captured_prompt_avatars[0] is None


class TestVideoChainingAvatarCharacterContext:
    """Integration of character descriptions into sub-scene LLM prompt."""

    @pytest.mark.asyncio
    async def test_character_context_included_in_system_prompt(
        self, db_session, regular_user, temp_storage
    ):
        """The LLM system prompt includes CHARACTERS block when avatars provided."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        avatar_ref = str(Path(temp_storage) / "bob_ref.png")
        Path(avatar_ref).write_bytes(b"fake-avatar-png")

        scene = _scene(
            1, start=0.0, end=10.0,
            image_prompt="Bob walks through the forest",
            reference_image_path=avatar_ref,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        avatars = [
            {
                "id": str(uuid4()),
                "name": "Bob",
                "gender": "male",
                "bio": "A mysterious informant with a dark past",
                "role": "Supporting character",
                "primary_image_path": avatar_ref,
                "consistency_strategy": "character_sheet",
                "deleted": False,
            }
        ]

        gen_video_mock = _make_video_mock(temp_storage)

        captured_llm_calls = []

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        # Mock LLMClient to capture system prompt
        llm_instance = MagicMock()
        llm_instance.generate = AsyncMock(
            return_value='["Bob enters the forest", "Bob discovers a clue"]'
        )

        plugin = TestVideoChainPlugin()

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
            patch("app.services.llm_service.LLMClient") as llm_cls_mock,
        ):
            vp_mock.extract_frame = extract_mock
            llm_cls_mock.return_value = llm_instance

            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={"avatars": avatars},
            )

        # Verify LLM was called with character context in system prompt
        assert llm_instance.generate.called
        llm_call_args = llm_instance.generate.call_args
        system_prompt = llm_call_args.kwargs.get("system", "")
        assert "CHARACTERS" in system_prompt
        assert "Bob" in system_prompt
        assert "male" in system_prompt
        assert "mysterious informant" in system_prompt
        assert "Supporting character" in system_prompt
        assert "visually consistent" in system_prompt

    @pytest.mark.asyncio
    async def test_no_character_context_when_no_avatars(
        self, db_session, regular_user, temp_storage
    ):
        """Without avatars, the system prompt should NOT include CHARACTERS block."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        scene = _scene(
            1, start=0.0, end=10.0,
            image_prompt="A peaceful meadow at dawn",
            reference_image_path=None,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        gen_video_mock = _make_video_mock(temp_storage)

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        llm_instance = MagicMock()
        llm_instance.generate = AsyncMock(
            return_value='["Meadow at dawn part 1", "Meadow at dawn part 2"]'
        )

        plugin = TestVideoChainPlugin()

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
            patch("app.services.llm_service.LLMClient") as llm_cls_mock,
        ):
            vp_mock.extract_frame = extract_mock
            llm_cls_mock.return_value = llm_instance

            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={},
            )

        assert llm_instance.generate.called
        system_prompt = llm_instance.generate.call_args.kwargs.get("system", "")
        assert "CHARACTERS" not in system_prompt

    @pytest.mark.asyncio
    async def test_deleted_avatar_excluded_from_character_context(
        self, db_session, regular_user, temp_storage
    ):
        """Deleted avatars should not appear in the CHARACTERS prompt block."""
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        avatar_ref = str(Path(temp_storage) / "eve_ref.png")
        Path(avatar_ref).write_bytes(b"fake-avatar-png")

        scene = _scene(
            1, start=0.0, end=10.0,
            image_prompt="Eve walks through the city",
            reference_image_path=avatar_ref,
        )
        scene.job_id = job.id
        db_session.add(scene)
        await db_session.commit()

        avatars = [
            {
                "id": str(uuid4()),
                "name": "Eve",
                "gender": "female",
                "bio": "A spy on a mission",
                "role": "Protagonist",
                "primary_image_path": avatar_ref,
                "consistency_strategy": "character_sheet",
                "deleted": True,  # Soft-deleted
            }
        ]

        gen_video_mock = _make_video_mock(temp_storage)

        async def _fake_extract_frame(video_path, image_path, ratio=0.8):
            Path(image_path).write_bytes(b"fake-seed-frame")

        extract_mock = AsyncMock(side_effect=_fake_extract_frame)

        llm_instance = MagicMock()
        llm_instance.generate = AsyncMock(
            return_value='["Eve walks part 1", "Eve walks part 2"]'
        )

        plugin = TestVideoChainPlugin()

        with (
            patch(PATCH_GEN_VIDEO, gen_video_mock),
            patch(PATCH_VIDEO_PROCESSOR) as vp_mock,
            patch("app.services.llm_service.LLMClient") as llm_cls_mock,
        ):
            vp_mock.extract_frame = extract_mock
            llm_cls_mock.return_value = llm_instance

            await plugin.generate_videos(
                db=db_session,
                job=job,
                scenes=[scene],
                context={"avatars": avatars},
            )

        system_prompt = llm_instance.generate.call_args.kwargs.get("system", "")
        assert "CHARACTERS" not in system_prompt
        assert "Eve" not in system_prompt
