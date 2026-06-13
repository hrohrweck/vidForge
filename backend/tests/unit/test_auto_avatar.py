"""Unit tests for auto-avatar creation in PluginBase.enrich_inputs()."""

import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import Avatar, AvatarImage, Job, JobObjectRef, ObjectRef, VideoScene
from app.plugins.base import PluginBase


class TestAutoAvatarPlugin(PluginBase):
    """Minimal plugin for testing auto-avatar behaviour."""

    @property
    def plugin_id(self) -> str:
        return "test_auto_avatar"

    @property
    def display_name(self) -> str:
        return "Test Auto Avatar"

    @property
    def description(self) -> str:
        return "Test plugin for auto-avatar unit tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        return {"scene_count": 1}


VALID_LLM_RESPONSE = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A young detective with sharp instincts.", '
    '"role": "Lead investigator"}, '
    '{"name": "Bob", "gender": "male", '
    '"bio": "A mysterious informant.", '
    '"role": "Supporting character"}'
    "]}"
)

VALID_LLM_FENCED = (
    "```json\n"
    + VALID_LLM_RESPONSE
    + "\n```"
)

INVALID_LLM_RESPONSE = "Sure, here are some characters: Alice (detective), Bob (informant)..."

SINGLE_CHAR_RESPONSE = (
    '{"characters": [{"name": "Alice", "gender": "female", '
    '"bio": "A detective.", "role": "Lead"}]}'
)

SINGLE_CHAR_RESPONSE_2 = (
    '{"characters": [{"name": "Eve", "gender": "female", '
    '"bio": "A spy.", "role": "Protagonist"}]}'
)

CHARS_WITH_OBJECTS_RESPONSE = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A young detective with sharp instincts.", '
    '"role": "Lead investigator"}'
    "],"
    '"objects": ['
    '{"name": "Notebook", "description": "A leather-bound detective notebook.", '
    '"visual_properties": {"color": "brown", "size": "small"}, '
    '"role": "Alice\'s evidence log"}, '
    '{"name": "Magnifying Glass", "description": "A brass magnifying glass.", '
    '"visual_properties": {"color": "gold", "make": "antique"}, '
    '"role": "Investigation tool"}'
    "]}"
)

CHARS_ONLY_NO_OBJECTS_RESPONSE = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A detective.", "role": "Lead"}'
    "],"
    '"objects": []'
    "}"
)

SIX_OBJECTS_RESPONSE = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A detective.", "role": "Lead"}'
    "],"
    '"objects": ['
    '{"name": "Obj1", "description": "Desc1", "visual_properties": {}, "role": "r1"}, '
    '{"name": "Obj2", "description": "Desc2", "visual_properties": {}, "role": "r2"}, '
    '{"name": "Obj3", "description": "Desc3", "visual_properties": {}, "role": "r3"}, '
    '{"name": "Obj4", "description": "Desc4", "visual_properties": {}, "role": "r4"}, '
    '{"name": "Obj5", "description": "Desc5", "visual_properties": {}, "role": "r5"}, '
    '{"name": "Obj6", "description": "Desc6", "visual_properties": {}, "role": "r6"}'
    "]}"
)

OBJECT_MISSING_PROPS_RESPONSE = (
    '{"characters": ['
    '{"name": "Alice", "gender": "female", '
    '"bio": "A detective.", "role": "Lead"}'
    "],"
    '"objects": ['
    '{"name": "Lamp", "description": "A desk lamp.", '
    '"role": "Lighting"}'
    "]}"
)

OBJECTS_ONLY_RESPONSE = (
    '{"characters": [],'
    '"objects": ['
    '{"name": "Sports Car", "description": "A red Ferrari F40.", '
    '"visual_properties": {"color": "red", "make": "Ferrari", "model": "F40"}, '
    '"role": "Protagonist\'s vehicle"}'
    "]}"
)

ALL_MISSING_RESPONSE = (
    '{"characters": [], "objects": []}'
)


def make_job(user_id, prompt="A noir detective story in 1920s Chicago"):
    return Job(
        id=uuid4(),
        user_id=user_id,
        status="pending",
        input_data={"prompt": prompt},
    )


def _make_gen_image_mock(tmp_dir):
    """Return an AsyncMock that writes a real file to tmp_dir and returns its path."""

    async def _gen_image(*, db, job, prompt, scene_number, model_preference,
                         aspect_ratio, title, **kwargs):
        fname = f"{title or 'avatar'}.png"
        fpath = os.path.join(tmp_dir, fname)
        Path(fpath).write_bytes(b"fake-png-data")
        return (fname, "test-model", uuid4(), Decimal("0"))

    return AsyncMock(side_effect=_gen_image)


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory and patch settings.storage_path."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.storage_path = tmp
            yield tmp


PATCH_LLM = "app.services.llm_service.LLMClient"
PATCH_GEN_IMAGE = "app.services.media_generator.generate_image"
PATCH_PREFS = "app.api.models.get_default_model_preferences"
PATCH_LOGGER = "app.plugins.base.logger"


class TestEnrichInputsAutoAvatar:

    @pytest.mark.asyncio
    async def test_empty_avatars_triggers_auto_creation(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin.enrich_inputs(db_session, job, {"avatars": []})

        assert "avatars" in ctx
        assert len(ctx["avatars"]) == 2
        assert ctx["avatars"][0]["name"] == "Alice"
        assert ctx["avatars"][0]["gender"] == "female"
        assert ctx["avatars"][1]["name"] == "Bob"
        assert ctx["avatars"][1]["role"] == "Supporting character"

        result = await db_session.execute(
            select(Avatar).where(Avatar.user_id == regular_user.id)
        )
        avatars = result.scalars().all()
        assert len(avatars) == 2

    @pytest.mark.asyncio
    async def test_non_empty_avatars_skips_auto_creation(
        self, db_session, regular_user
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin.enrich_inputs(
                db_session, job, {"avatars": [{"id": "fake", "name": "Existing"}]}
            )

        assert ctx["avatars"] == [{"id": "fake", "name": "Existing"}]
        llm_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_prompt_skips_auto_creation(
        self, db_session, regular_user
    ):
        job = Job(
            id=uuid4(),
            user_id=regular_user.id,
            status="pending",
            input_data={"style": "cinematic"},
        )
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin.enrich_inputs(db_session, job, {"avatars": []})

        assert ctx["avatars"] == []
        llm_mock.assert_not_called()


class TestCreateAutoAvatarsLLM:

    @pytest.mark.asyncio
    async def test_valid_json_characters_parsed(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(db_session, job, {"avatars": []})

        assert len(ctx["avatars"]) == 2
        a = ctx["avatars"][0]
        assert a["name"] == "Alice"
        assert a["gender"] == "female"
        assert a["role"] == "Lead investigator"
        assert a["primary_image_path"] is not None

        result = await db_session.execute(
            select(AvatarImage).join(
                Avatar, AvatarImage.avatar_id == Avatar.id
            ).where(Avatar.user_id == regular_user.id)
        )
        images = result.scalars().all()
        assert len(images) == 2

    @pytest.mark.asyncio
    async def test_invalid_json_logged_and_skipped(
        self, db_session, regular_user
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=INVALID_LLM_RESPONSE)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        assert ctx == {"avatars": [], "objects": []}
        assert log_mock.warning.called

    @pytest.mark.asyncio
    async def test_llm_unavailable_skips(
        self, db_session, regular_user
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            llm_cls.return_value.generate = AsyncMock(
                side_effect=ConnectionError("Ollama is down")
            )
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        assert ctx == {"avatars": [], "objects": []}
        assert log_mock.warning.called

    @pytest.mark.asyncio
    async def test_fenced_json_parsed(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=VALID_LLM_FENCED)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        assert len(ctx["avatars"]) == 2


class TestCreateAutoAvatarsImageGen:

    @pytest.mark.asyncio
    async def test_image_gen_failure_creates_avatar_without_image(
        self, db_session, regular_user
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=SINGLE_CHAR_RESPONSE)
        gen_image_mock = AsyncMock(side_effect=RuntimeError("GPU out of memory"))
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        assert len(ctx["avatars"]) == 1
        assert ctx["avatars"][0]["primary_image_path"] is None
        assert ctx["avatars"][0]["all_image_paths"] == []
        assert log_mock.warning.called

        result = await db_session.execute(
            select(Avatar).where(Avatar.user_id == regular_user.id)
        )
        avatars = result.scalars().all()
        assert len(avatars) == 1
        assert avatars[0].name == "Alice"

    @pytest.mark.asyncio
    async def test_image_file_not_on_disk_still_persists_avatar(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=SINGLE_CHAR_RESPONSE_2)
        gen_image_mock = AsyncMock(
            return_value=("nonexistent/eve.png", "test-model", uuid4(), Decimal("0"))
        )
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        assert len(ctx["avatars"]) == 1
        assert ctx["avatars"][0]["primary_image_path"] is None
        assert log_mock.error.called


class TestCreateAutoAvatarsPrompt:

    @pytest.mark.asyncio
    async def test_enhanced_prompt_takes_precedence(
        self, db_session, regular_user, temp_storage
    ):
        job = Job(
            id=uuid4(),
            user_id=regular_user.id,
            status="pending",
            input_data={
                "prompt": "raw idea",
                "enhanced_prompt": "A noir thriller in rain-soaked Tokyo",
            },
        )
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()
        llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        call_args = llm_mock.call_args
        assert "noir thriller" in str(call_args)

    @pytest.mark.asyncio
    async def test_empty_prompt_skips(self, db_session, regular_user):
        job = Job(
            id=uuid4(),
            user_id=regular_user.id,
            status="pending",
            input_data={"prompt": ""},
        )
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()
        llm_mock = AsyncMock(return_value=VALID_LLM_RESPONSE)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        assert ctx == {"avatars": [], "objects": []}
        llm_mock.assert_not_called()


def _scene(scene_number: int, image_prompt: str = "A sunny day") -> VideoScene:
    """Create a minimal VideoScene for generate_images tests."""
    return VideoScene(
        id=uuid4(),
        scene_number=scene_number,
        start_time=scene_number,
        end_time=scene_number + 5,
        image_prompt=image_prompt,
        status="pending",
    )


class TestGenerateImagesAvatar:

    @pytest.mark.asyncio
    async def test_generate_images_avatar_passes_reference(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        ref_path = Path(temp_storage) / "avatar_ref.png"
        ref_path.write_bytes(b"fake-reference-png")

        plugin = TestAutoAvatarPlugin()
        scenes = [_scene(1, "A detective walks through fog")]

        context = {
            "avatars": [
                {
                    "id": "uuid-1",
                    "name": "Alice",
                    "primary_image_path": str(ref_path),
                }
            ]
        }

        captured_kwargs: dict = {}
        async def _gen_image(*, db, job, prompt, scene_number,
                             model_preference, provider_id=None,
                             reference_image_path=None,
                             reference_image_strength=None,
                             **kwargs):
            captured_kwargs["reference_image_path"] = reference_image_path
            captured_kwargs["reference_image_strength"] = reference_image_strength
            fpath = Path(temp_storage) / "scene1.png"
            fpath.write_bytes(b"fake-scene-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin.generate_images(db_session, job, scenes, context)

        assert captured_kwargs["reference_image_path"] == str(ref_path)
        assert captured_kwargs["reference_image_strength"] == 0.75

    @pytest.mark.asyncio
    async def test_generate_images_avatar_without_avatars_no_reference(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()
        scenes = [_scene(1, "A sunset over mountains")]

        captured_kwargs: dict = {}

        async def _gen_image(*, db, job, prompt, scene_number,
                             model_preference, provider_id=None,
                             reference_image_path=None,
                             reference_image_strength=None,
                             **kwargs):
            captured_kwargs["reference_image_path"] = reference_image_path
            captured_kwargs["reference_image_strength"] = reference_image_strength
            fpath = Path(temp_storage) / "scene1.png"
            fpath.write_bytes(b"fake-scene-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)

        with patch(PATCH_GEN_IMAGE, gen_image_mock):
            await plugin.generate_images(db_session, job, scenes, {})

        assert captured_kwargs["reference_image_path"] is None

    @pytest.mark.asyncio
    async def test_generate_images_avatar_missing_primary_image_warns(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()
        scenes = [_scene(1, "Underwater exploration")]

        context = {
            "avatars": [
                {
                    "id": "uuid-2",
                    "name": "Bob",
                }
            ]
        }

        captured_kwargs: dict = {}

        async def _gen_image(*, db, job, prompt, scene_number,
                             model_preference, provider_id=None,
                             reference_image_path=None,
                             reference_image_strength=None,
                             **kwargs):
            captured_kwargs["reference_image_path"] = reference_image_path
            fpath = Path(temp_storage) / "scene1.png"
            fpath.write_bytes(b"fake-scene-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)

        with (
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            await plugin.generate_images(db_session, job, scenes, context)

        assert captured_kwargs["reference_image_path"] is None
        assert log_mock.warning.called

    @pytest.mark.asyncio
    async def test_generate_images_avatar_file_missing_on_disk_warns(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()
        scenes = [_scene(1, "A desert landscape")]

        nonexistent = str(Path(temp_storage) / "does_not_exist.png")

        context = {
            "avatars": [
                {
                    "id": "uuid-3",
                    "name": "Charlie",
                    "primary_image_path": nonexistent,
                }
            ]
        }

        captured_kwargs: dict = {}

        async def _gen_image(*, db, job, prompt, scene_number,
                             model_preference, provider_id=None,
                             reference_image_path=None,
                             **kwargs):
            captured_kwargs["reference_image_path"] = reference_image_path
            fpath = Path(temp_storage) / "scene1.png"
            fpath.write_bytes(b"fake-scene-image")
            return (str(fpath), "test-model", uuid4(), Decimal("0"))

        gen_image_mock = AsyncMock(side_effect=_gen_image)

        with (
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            await plugin.generate_images(db_session, job, scenes, context)

        assert captured_kwargs["reference_image_path"] is None
        assert log_mock.warning.called


class TestCreateAutoObjects:

    @pytest.mark.asyncio
    async def test_characters_and_objects_both_processed(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=CHARS_WITH_OBJECTS_RESPONSE)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(db_session, job, {})
        assert len(ctx["avatars"]) == 1
        assert ctx["avatars"][0]["name"] == "Alice"
        assert len(ctx["objects"]) == 2
        assert ctx["objects"][0]["name"] == "Notebook"
        assert ctx["objects"][0]["visual_properties"] == {"color": "brown", "size": "small"}
        assert ctx["objects"][0]["role"] == "Alice's evidence log"
        assert ctx["objects"][0]["primary_image_path"] is None
        assert ctx["objects"][1]["name"] == "Magnifying Glass"

        result = await db_session.execute(
            select(ObjectRef).where(ObjectRef.user_id == regular_user.id)
        )
        objects = result.scalars().all()
        assert len(objects) == 2
        assert objects[0].name == "Notebook"
        assert objects[0].visual_properties == {"color": "brown", "size": "small"}

        result = await db_session.execute(
            select(JobObjectRef).where(JobObjectRef.job_id == job.id)
        )
        links = result.scalars().all()
        assert len(links) == 2
        link_roles = {link.role for link in links}
        assert link_roles == {"Alice's evidence log", "Investigation tool"}
        assert all(link.importance_score is None for link in links)

    @pytest.mark.asyncio
    async def test_characters_only_no_objects(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=CHARS_ONLY_NO_OBJECTS_RESPONSE)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(db_session, job, {})
        assert len(ctx["avatars"]) == 1
        assert "objects" in ctx
        assert ctx["objects"] == []

        result = await db_session.execute(
            select(ObjectRef).where(ObjectRef.user_id == regular_user.id)
        )
        assert len(result.scalars().all()) == 0

    @pytest.mark.asyncio
    async def test_six_objects_capped_at_five(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=SIX_OBJECTS_RESPONSE)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(db_session, job, {})
        assert len(ctx["objects"]) == 5
        assert ctx["objects"][-1]["name"] == "Obj5"

        result = await db_session.execute(
            select(ObjectRef).where(ObjectRef.user_id == regular_user.id)
        )
        assert len(result.scalars().all()) == 5

    @pytest.mark.asyncio
    async def test_object_missing_visual_properties(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=OBJECT_MISSING_PROPS_RESPONSE)
        gen_image_mock = _make_gen_image_mock(temp_storage)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_GEN_IMAGE, gen_image_mock),
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(db_session, job, {})
        assert len(ctx["objects"]) == 1
        assert ctx["objects"][0]["name"] == "Lamp"
        assert ctx["objects"][0]["description"] == "A desk lamp."
        assert ctx["objects"][0]["visual_properties"] is None

    @pytest.mark.asyncio
    async def test_parse_failure_returns_context_unchanged(
        self, db_session, regular_user
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=INVALID_LLM_RESPONSE)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
            patch(PATCH_LOGGER) as log_mock,
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )

        assert ctx == {"avatars": [], "objects": []}
        assert log_mock.warning.called

        result = await db_session.execute(
            select(ObjectRef).where(ObjectRef.user_id == regular_user.id)
        )
        assert len(result.scalars().all()) == 0

    @pytest.mark.asyncio
    async def test_objects_only_no_characters(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=OBJECTS_ONLY_RESPONSE)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(db_session, job, {})
        assert "avatars" in ctx
        assert ctx["avatars"] == []
        assert len(ctx["objects"]) == 1
        assert ctx["objects"][0]["name"] == "Sports Car"
        assert ctx["objects"][0]["visual_properties"] == {
            "color": "red", "make": "Ferrari", "model": "F40"
        }

    @pytest.mark.asyncio
    async def test_all_missing_returns_empty(
        self, db_session, regular_user, temp_storage
    ):
        job = make_job(regular_user.id)
        db_session.add(job)
        await db_session.commit()

        plugin = TestAutoAvatarPlugin()

        llm_mock = AsyncMock(return_value=ALL_MISSING_RESPONSE)
        prefs_mock = AsyncMock(return_value={"text_to_image_model": "flux1-schnell"})

        with (
            patch(PATCH_LLM) as llm_cls,
            patch(PATCH_PREFS, prefs_mock),
        ):
            llm_cls.return_value.generate = llm_mock
            ctx = await plugin._create_auto_avatars(
                db_session, job, {"avatars": []}
            )
        assert ctx["avatars"] == []
        assert ctx["objects"] == []
