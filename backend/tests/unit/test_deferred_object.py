"""Unit tests for deferred object reference image generation."""

import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, ObjectRef, ObjectRefImage
from app.plugins.base import PluginBase


class _TestPlugin(PluginBase):
    """Minimal plugin so we can call _generate_object_references."""

    @property
    def plugin_id(self) -> str:
        return "test_deferred_object"

    @property
    def display_name(self) -> str:
        return "Test Deferred Object"

    @property
    def description(self) -> str:
        return "Test plugin for deferred object reference tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        return {"scene_count": 1}


PATCH_GEN_IMAGE = "app.services.media_generator.generate_image"


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


async def _create_object_ref(db: AsyncSession, user_id, name: str) -> ObjectRef:
    """Create and persist an ObjectRef, returning it with its id assigned."""
    obj = ObjectRef(
        user_id=user_id,
        name=name,
        description=f"Description for {name}",
        visual_properties={"color": "blue"},
        category="prop",
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


class TestDeferredObject:

    @pytest.mark.asyncio
    async def test_selection_one_of_three_calls_generate_image_once(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """Planner selected 1 of 3 objects → only 1 generate_image call made."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()
        notebook = await _create_object_ref(db_session, user_id, "Notebook")
        magnifier = await _create_object_ref(db_session, user_id, "Magnifying Glass")
        candle = await _create_object_ref(db_session, user_id, "Candle")

        context = {
            "objects": [
                {"id": str(notebook.id), "name": "Notebook", "primary_image_path": None},
                {"id": str(magnifier.id), "name": "Magnifying Glass", "primary_image_path": None},
                {"id": str(candle.id), "name": "Candle", "primary_image_path": None},
            ],
            "object_selections": [
                {
                    "object_name": "Notebook",
                    "seed_image_prompt": "A brown leather notebook on a wooden desk",
                    "scenes": [1, 2, 3],
                }
            ],
        }

        call_count = 0

        async def _gen_image(*, db, job, prompt, scene_number,
                             model_preference, provider_id=None,
                             **kwargs):
            nonlocal call_count
            call_count += 1
            fpath = Path(temp_storage) / "obj_ref_notebook.png"
            fpath.write_bytes(b"fake-object-ref-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _TestPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin._generate_object_references(db_session, job, context)

        assert call_count == 1

        notebook_ctx = next(o for o in context["objects"] if o["name"] == "Notebook")
        assert notebook_ctx["primary_image_path"] is not None
        assert "obj_ref_notebook.png" in notebook_ctx["primary_image_path"]

        for name in ("Magnifying Glass", "Candle"):
            obj_ctx = next(o for o in context["objects"] if o["name"] == name)
            assert obj_ctx["primary_image_path"] is None

    @pytest.mark.asyncio
    async def test_no_selections_no_generate_image_calls(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """Planner selected 0 objects → no generate_image calls."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        notebook = await _create_object_ref(db_session, user_id, "Notebook")

        context = {
            "objects": [
                {"id": str(notebook.id), "name": "Notebook", "primary_image_path": None},
            ],
            "object_selections": [],
        }

        call_count = 0

        async def _gen_image(**kwargs):
            nonlocal call_count
            call_count += 1
            return ("/fake/path", "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _TestPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin._generate_object_references(db_session, job, context)

        assert call_count == 0

    @pytest.mark.asyncio
    async def test_generate_image_fails_object_stays_text_only(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """generate_image fails → object stays text-only, other objects unaffected."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        notebook = await _create_object_ref(db_session, user_id, "Notebook")
        magnifier = await _create_object_ref(db_session, user_id, "Magnifying Glass")

        context = {
            "objects": [
                {"id": str(notebook.id), "name": "Notebook", "primary_image_path": None},
                {"id": str(magnifier.id), "name": "Magnifying Glass", "primary_image_path": None},
            ],
            "object_selections": [
                {
                    "object_name": "Notebook",
                    "seed_image_prompt": "A brown leather notebook",
                    "scenes": [1],
                },
                {
                    "object_name": "Magnifying Glass",
                    "seed_image_prompt": "A brass magnifying glass",
                    "scenes": [2],
                },
            ],
        }

        call_count = 0

        async def _gen_image(*, prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if "notebook" in prompt.lower():
                raise ValueError("Invalid prompt — non-recoverable")
            fpath = Path(temp_storage) / "obj_ref_magnifier.png"
            fpath.write_bytes(b"fake-magnifier-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _TestPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin._generate_object_references(db_session, job, context)

        notebook_ctx = next(o for o in context["objects"] if o["name"] == "Notebook")
        assert notebook_ctx["primary_image_path"] is None

        magnifier_ctx = next(o for o in context["objects"] if o["name"] == "Magnifying Glass")
        assert magnifier_ctx["primary_image_path"] is not None

    @pytest.mark.asyncio
    async def test_context_objects_updated_with_primary_image_path(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """context["objects"] updated with primary_image_path for selected object."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        notebook = await _create_object_ref(db_session, user_id, "Notebook")

        context = {
            "objects": [
                {"id": str(notebook.id), "name": "Notebook", "primary_image_path": None},
            ],
            "object_selections": [
                {
                    "object_name": "Notebook",
                    "seed_image_prompt": "A brown leather notebook on a desk",
                    "scenes": [1, 2],
                }
            ],
        }

        async def _gen_image(**kwargs):
            fpath = Path(temp_storage) / "obj_ref_notebook.png"
            fpath.write_bytes(b"fake-notebook-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _TestPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin._generate_object_references(db_session, job, context)

        notebook_ctx = context["objects"][0]
        assert notebook_ctx["primary_image_path"] is not None
        assert "obj_ref_notebook.png" in notebook_ctx["primary_image_path"]
        assert Path(notebook_ctx["primary_image_path"]).exists()

    @pytest.mark.asyncio
    async def test_object_ref_image_persisted_to_db(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """ObjectRefImage row created in the database for the selected object."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        notebook = await _create_object_ref(db_session, user_id, "Notebook")

        context = {
            "objects": [
                {"id": str(notebook.id), "name": "Notebook", "primary_image_path": None},
            ],
            "object_selections": [
                {
                    "object_name": "Notebook",
                    "seed_image_prompt": "A brown leather notebook",
                    "scenes": [1],
                }
            ],
        }

        async def _gen_image(**kwargs):
            fpath = Path(temp_storage) / "obj_ref_notebook.png"
            fpath.write_bytes(b"fake-notebook-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _TestPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin._generate_object_references(db_session, job, context)

        result = await db_session.execute(
            select(ObjectRefImage).where(ObjectRefImage.object_ref_id == notebook.id)
        )
        images = result.scalars().all()
        assert len(images) == 1
        assert images[0].is_primary is True
        assert "obj_ref_notebook.png" in images[0].storage_path

    @pytest.mark.asyncio
    async def test_empty_object_selections_returns_early(
        self, db_session: AsyncSession, regular_user
    ):
        """Missing object_selections key → method returns early without error."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        context = {
            "objects": [
                {"id": str(uuid4()), "name": "Notebook", "primary_image_path": None},
            ],
        }

        plugin = _TestPlugin()

        await plugin._generate_object_references(db_session, job, context)

        assert context["objects"][0]["primary_image_path"] is None

    @pytest.mark.asyncio
    async def test_planner_selection_without_matching_object_skipped(
        self, db_session: AsyncSession, regular_user, temp_storage
    ):
        """Planner selected an object that doesn't exist in context.objects → skipped."""
        user_id = regular_user.id
        job = _make_job(user_id)
        db_session.add(job)
        await db_session.commit()

        notebook = await _create_object_ref(db_session, user_id, "Notebook")

        context = {
            "objects": [
                {"id": str(notebook.id), "name": "Notebook", "primary_image_path": None},
            ],
            "object_selections": [
                {
                    "object_name": "GhostCar",
                    "seed_image_prompt": "A ghost car",
                    "scenes": [1],
                },
                {
                    "object_name": "Notebook",
                    "seed_image_prompt": "A leather notebook",
                    "scenes": [2],
                },
            ],
        }

        call_prompts = []

        async def _gen_image(*, prompt, **kwargs):
            call_prompts.append(prompt)
            fpath = Path(temp_storage) / "obj_ref_test.png"
            fpath.write_bytes(b"fake-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)
        plugin = _TestPlugin()

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin._generate_object_references(db_session, job, context)

        assert len(call_prompts) == 1
        assert "leather notebook" in call_prompts[0]
