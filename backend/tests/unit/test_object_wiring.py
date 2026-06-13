"""Tests for object reference wiring in generate_images and generate_videos."""

import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, VideoScene
from app.plugins.base import PluginBase


class _ObjectWiringPlugin(PluginBase):
    """Minimal plugin for testing object reference wiring."""

    @property
    def plugin_id(self) -> str:
        return "test_object_wiring"

    @property
    def display_name(self) -> str:
        return "Test Object Wiring"

    @property
    def description(self) -> str:
        return "Test plugin for object wiring tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        return {"scene_count": 1}


PATCH_GEN_IMAGE = "app.services.media_generator.generate_image"
PATCH_GEN_VIDEO = "app.services.media_generator.generate_video"


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory and patch settings.storage_path."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.storage_path = tmp
            yield tmp


def _make_job(user_id) -> Job:
    return Job(
        id=uuid4(),
        user_id=user_id,
        input_data={"prompt": "A test scene", "image_model": "flux1-schnell"},
        status="generating_images",
        progress=20,
    )


def _make_scene(job_id, scene_number: int, image_prompt: str = "A scenic view"):
    return VideoScene(
        id=uuid4(),
        job_id=job_id,
        scene_number=scene_number,
        start_time=(scene_number - 1) * 5.0,
        end_time=scene_number * 5.0,
        image_prompt=image_prompt,
        visual_description=image_prompt,
        mood="neutral",
    )


class TestGenerateImagesObjectWiring:

    @pytest.mark.asyncio
    async def test_scene_with_object_selection_injects_visual_properties(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """When a scene has a matching object selection with primary_image_path
        and visual_properties, the prompt passed to generate_image includes
        [Object reference: ...]."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        scene = _make_scene(job.id, 1, image_prompt="A car on a highway")
        db_session.add(scene)
        await db_session.commit()

        context = {
            "objects": [
                {
                    "id": str(uuid4()),
                    "name": "Sports Car",
                    "primary_image_path": str(Path(temp_storage) / "car_ref.png"),
                    "visual_properties": {"color": "red", "make": "Ferrari", "model": "F40"},
                }
            ],
            "object_selections": [
                {
                    "object_name": "Sports Car",
                    "importance_score": 0.9,
                    "seed_image_prompt": "A red Ferrari F40 sports car",
                    "scenes": [1],
                }
            ],
        }

        received_prompt: str | None = None

        async def _gen_image(*, prompt, **kwargs):
            nonlocal received_prompt
            received_prompt = prompt
            fpath = Path(temp_storage) / "scene_1_seed.png"
            fpath.write_bytes(b"fake-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _ObjectWiringPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin.generate_images(db_session, job, [scene], context)

        assert received_prompt is not None
        assert "[Object reference:" in received_prompt
        assert "color=red" in received_prompt
        assert "make=Ferrari" in received_prompt

    @pytest.mark.asyncio
    async def test_scene_without_objects_does_not_inject(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """When context has no objects, the prompt is unchanged."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        scene = _make_scene(job.id, 1, image_prompt="Plain landscape")
        db_session.add(scene)
        await db_session.commit()

        context: dict = {}

        received_prompt: str | None = None

        async def _gen_image(*, prompt, **kwargs):
            nonlocal received_prompt
            received_prompt = prompt
            fpath = Path(temp_storage) / "scene_1_seed.png"
            fpath.write_bytes(b"fake-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _ObjectWiringPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin.generate_images(db_session, job, [scene], context)

        assert received_prompt == "Plain landscape"

    @pytest.mark.asyncio
    async def test_empty_object_selections_no_injection(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """When object_selections is empty, no prompt injection occurs."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        scene = _make_scene(job.id, 1, image_prompt="A forest scene")
        db_session.add(scene)
        await db_session.commit()

        context = {
            "objects": [
                {
                    "id": str(uuid4()),
                    "name": "Lantern",
                    "primary_image_path": str(Path(temp_storage) / "lantern.png"),
                    "visual_properties": {"color": "gold", "type": "paper"},
                }
            ],
            "object_selections": [],
        }

        received_prompt: str | None = None

        async def _gen_image(*, prompt, **kwargs):
            nonlocal received_prompt
            received_prompt = prompt
            fpath = Path(temp_storage) / "scene_1_seed.png"
            fpath.write_bytes(b"fake-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _ObjectWiringPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin.generate_images(db_session, job, [scene], context)

        assert received_prompt == "A forest scene"

    @pytest.mark.asyncio
    async def test_object_without_primary_image_path_excluded(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """When the matching object has no primary_image_path, no injection occurs."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        scene = _make_scene(job.id, 1, image_prompt="A desk with items")
        db_session.add(scene)
        await db_session.commit()

        context = {
            "objects": [
                {
                    "id": str(uuid4()),
                    "name": "Notebook",
                    "primary_image_path": None,
                    "visual_properties": {"color": "brown", "material": "leather"},
                }
            ],
            "object_selections": [
                {
                    "object_name": "Notebook",
                    "importance_score": 0.8,
                    "seed_image_prompt": "A brown leather notebook",
                    "scenes": [1],
                }
            ],
        }

        received_prompt: str | None = None

        async def _gen_image(*, prompt, **kwargs):
            nonlocal received_prompt
            received_prompt = prompt
            fpath = Path(temp_storage) / "scene_1_seed.png"
            fpath.write_bytes(b"fake-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _ObjectWiringPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin.generate_images(db_session, job, [scene], context)

        assert received_prompt == "A desk with items"


class TestGenerateVideosObjectWiring:

    @pytest.mark.asyncio
    async def test_short_scene_injects_object_visual_properties(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """Short scene (≤5s) with object selection injects visual properties
        into the prompt passed to generate_video."""
        user_id = regular_user.id
        job = _make_job(user_id)
        if job.input_data is None:
            job.input_data = {}
        job.input_data["video_model"] = "wan2.2"
        job.input_data["duration"] = 5
        db_session.add(job)
        await db_session.commit()

        scene = VideoScene(
            id=uuid4(),
            job_id=job.id,
            scene_number=1,
            start_time=0.0,
            end_time=4.0,
            image_prompt="A car driving",
            visual_description="A red car driving on a coastal road",
            reference_image_path=str(Path(temp_storage) / "scene_1_seed.png"),
            mood="energetic",
        )
        db_session.add(scene)

        # Also need an empty scene list for the second part of generate_videos
        # (import _import_scene_asset)
        await db_session.commit()

        context = {
            "objects": [
                {
                    "id": str(uuid4()),
                    "name": "Sports Car",
                    "primary_image_path": str(Path(temp_storage) / "car_ref.png"),
                    "visual_properties": {"color": "red", "make": "Ferrari"},
                }
            ],
            "object_selections": [
                {
                    "object_name": "Sports Car",
                    "importance_score": 0.9,
                    "seed_image_prompt": "A red Ferrari",
                    "scenes": [1],
                }
            ],
        }

        received_prompt: str | None = None

        async def _gen_video(*, prompt, **kwargs):
            nonlocal received_prompt
            received_prompt = prompt
            fpath = Path(temp_storage) / "scene_1_video.mp4"
            fpath.write_bytes(b"fake-video")
            return (str(fpath), "test-model", uuid4(), 4.0, None, Decimal("0"))

        gen_video_mock = AsyncMock(side_effect=_gen_video)

        plugin = _ObjectWiringPlugin()
        with patch(PATCH_GEN_VIDEO, gen_video_mock), \
             patch("app.services.video_processor.VideoProcessor.extract_frame",
                   AsyncMock()), \
             patch("app.services.video_processor.VideoProcessor.validate_video_output",
                   new_callable=AsyncMock, return_value=None):
            await plugin.generate_videos(db_session, job, [scene], context)

        assert received_prompt is not None
        assert "[Object reference:" in received_prompt
        assert "color=red" in received_prompt
