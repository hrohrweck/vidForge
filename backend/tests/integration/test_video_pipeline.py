"""Integration tests for full video pipeline validation.

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/test_video_pipeline.py -v
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import ErrorEvent, Job, ModelConfig, Provider, Template, User, VideoScene
from app.plugins.base import PluginBase
from app.services.media_generator import generate_video

pytestmark = pytest.mark.integration


class TestVideoPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "test_video_plugin"

    @property
    def display_name(self) -> str:
        return "Test Video Plugin"

    @property
    def description(self) -> str:
        return "A test plugin for video pipeline tests"

    def get_template_definition(self) -> dict:
        return {
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": ["plan_scenes", "generate_images", "generate_videos", "render"],
        }

    async def plan_scenes(self, db, job, context):
        return {"scene_count": 1}


def _create_test_video_file(path: str, duration: float = 5.0, fps: int = 16) -> None:
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c=black:s=320x240:r={fps}",
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-y",
        path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _create_1frame_video_file(path: str) -> None:
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "color=c=black:s=320x240:r=1",
        "-frames:v", "1",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-y",
        path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _mock_provider(video_bytes: bytes) -> MagicMock:
    mock = MagicMock()
    mock.config = {
        "wan_clip_name": "test_clip.safetensors",
        "wan_vae_name": "test_vae.safetensors",
        "wan_unet_name": "test_unet.safetensors",
    }
    mock.queue_prompt = AsyncMock(return_value="test-prompt-id")
    mock.wait_for_completion = AsyncMock(return_value={"outputs": {}})
    mock.get_output = AsyncMock(return_value=video_bytes)
    return mock


async def _seed_test_data(db_session: AsyncSession) -> dict:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    test_id = str(uuid4())[:8]

    user = User(
        id=uuid4(),
        email=f"video_pipeline_{test_id}@example.com",
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)

    provider = Provider(
        id=uuid4(),
        name=f"Test ComfyUI {test_id}",
        provider_type="comfyui_direct",
        config={"url": "http://localhost:8188"},
        is_active=True,
    )
    db_session.add(provider)

    model_config = ModelConfig(
        id=uuid4(),
        provider_id=provider.id,
        model_id="wan2.2_t2v",
        provider_model_id="wan2.2",
        display_name="Wan 2.2 T2V",
        modality="video",
        endpoint_type="comfyui",
        is_active=True,
    )
    db_session.add(model_config)

    result = await db_session.execute(select(Template).limit(1))
    template = result.scalar_one_or_none()
    if not template:
        pytest.skip("No templates available — seeding may have failed")

    job = Job(
        id=uuid4(),
        user_id=user.id,
        template_id=template.id,
        status="pending",
        stage="generating_videos",
        input_data={"prompt": "test video", "aspect_ratio": "16:9"},
    )
    db_session.add(job)

    scene = VideoScene(
        id=uuid4(),
        job_id=job.id,
        scene_number=1,
        start_time=0.0,
        end_time=5.0,
        visual_description="A beautiful sunset",
        status="pending",
    )
    db_session.add(scene)

    await db_session.commit()
    for obj in (user, provider, model_config, job, scene):
        await db_session.refresh(obj)

    return {
        "user": user,
        "provider": provider,
        "model_config": model_config,
        "job": job,
        "scene": scene,
    }


@pytest.fixture
async def video_pipeline_setup(db_session: AsyncSession):
    data = await _seed_test_data(db_session)
    yield data
    from app.config import get_settings

    settings = get_settings()
    job_output_dir = Path(settings.storage_path) / "output" / str(data["job"].id)
    if job_output_dir.exists():
        shutil.rmtree(job_output_dir)

    from sqlalchemy import delete as sa_delete

    await db_session.execute(sa_delete(ErrorEvent).where(ErrorEvent.source_id == data["scene"].id))
    await db_session.execute(sa_delete(VideoScene).where(VideoScene.id == data["scene"].id))
    await db_session.execute(sa_delete(Job).where(Job.id == data["job"].id))
    await db_session.execute(sa_delete(ModelConfig).where(ModelConfig.id == data["model_config"].id))
    await db_session.execute(sa_delete(Provider).where(Provider.id == data["provider"].id))
    await db_session.execute(sa_delete(User).where(User.id == data["user"].id))
    await db_session.commit()


@pytest.fixture
def no_sleep():
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep


@pytest.fixture
def valid_video_bytes() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        _create_test_video_file(tmp.name, duration=5.0, fps=16)
        with open(tmp.name, "rb") as f:
            data = f.read()
        os.unlink(tmp.name)
    return data


@pytest.fixture
def invalid_video_bytes() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        _create_1frame_video_file(tmp.name)
        with open(tmp.name, "rb") as f:
            data = f.read()
        os.unlink(tmp.name)
    return data


@pytest.mark.asyncio
async def test_generate_video_with_validation_passes(
    db_session: AsyncSession,
    video_pipeline_setup: dict,
    no_sleep: AsyncMock,
    valid_video_bytes: bytes,
):
    setup = video_pipeline_setup
    job = setup["job"]
    scene = setup["scene"]

    mock_provider = _mock_provider(valid_video_bytes)

    with patch(
        "app.services.media_generator.get_provider_instance",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        plugin = TestVideoPlugin()
        await plugin.generate_videos(
            db=db_session,
            job=job,
            scenes=[scene],
            context={},
        )

    await db_session.refresh(scene)

    assert scene.status == "video_ready"
    assert scene.generated_video_path is not None
    assert scene.generated_video_path != ""
    assert scene.error_message is None

    from app.config import get_settings

    settings = get_settings()
    video_full_path = Path(settings.storage_path) / scene.generated_video_path
    assert video_full_path.exists()
    assert video_full_path.stat().st_size > 0

    result = await db_session.execute(
        select(ErrorEvent).where(ErrorEvent.source_id == scene.id)
    )
    error_events = result.scalars().all()
    assert len(error_events) == 0


@pytest.mark.asyncio
async def test_generate_video_with_validation_fails_triggers_retry(
    db_session: AsyncSession,
    video_pipeline_setup: dict,
    no_sleep: AsyncMock,
    valid_video_bytes: bytes,
    invalid_video_bytes: bytes,
):
    setup = video_pipeline_setup
    job = setup["job"]
    scene = setup["scene"]

    mock_provider = _mock_provider(valid_video_bytes)
    mock_provider.get_output = AsyncMock(
        side_effect=[invalid_video_bytes, valid_video_bytes]
    )

    with patch(
        "app.services.media_generator.get_provider_instance",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        plugin = TestVideoPlugin()
        await plugin.generate_videos(
            db=db_session,
            job=job,
            scenes=[scene],
            context={},
        )

    await db_session.refresh(scene)

    assert scene.status == "video_ready"
    assert scene.generated_video_path is not None
    assert scene.error_message is None

    assert mock_provider.get_output.call_count == 2

    result = await db_session.execute(
        select(ErrorEvent).where(ErrorEvent.source_id == scene.id)
    )
    error_events = result.scalars().all()
    assert len(error_events) == 1
    assert error_events[0].origin.value == "video_generation"
    assert "frame" in error_events[0].message.lower()


@pytest.mark.asyncio
async def test_generate_video_with_validation_fails_after_3_retries(
    db_session: AsyncSession,
    video_pipeline_setup: dict,
    no_sleep: AsyncMock,
    invalid_video_bytes: bytes,
):
    setup = video_pipeline_setup
    job = setup["job"]
    scene = setup["scene"]

    mock_provider = _mock_provider(invalid_video_bytes)

    with patch(
        "app.services.media_generator.get_provider_instance",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        plugin = TestVideoPlugin()
        await plugin.generate_videos(
            db=db_session,
            job=job,
            scenes=[scene],
            context={},
        )

    await db_session.refresh(scene)

    assert scene.status == "failed"
    assert scene.generated_video_path is None
    assert scene.error_message is not None
    assert "frame" in scene.error_message.lower() or "invalid" in scene.error_message.lower()

    assert mock_provider.get_output.call_count == 4

    result = await db_session.execute(
        select(ErrorEvent).where(ErrorEvent.source_id == scene.id)
    )
    error_events = result.scalars().all()
    assert len(error_events) == 4

    for evt in error_events:
        assert evt.origin.value == "video_generation"
        assert evt.severity.value == "warning"
