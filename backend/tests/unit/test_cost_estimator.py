from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.database import Job, ModelConfig, Provider, User, VideoScene
from app.services.cost_estimator import (
    CostEstimate,
    estimate_job_cost,
    estimate_media_call,
    get_job_actual_cost,
    record_media_generation_cost,
)
from app.services.model_config_service import ModelConfigService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(*, db_session, provider_type="comfyui", **overrides) -> Provider:
    defaults: dict = {
        "id": uuid4(),
        "name": f"test-{provider_type}-{uuid4().hex[:6]}",
        "provider_type": provider_type,
        "config": {},
        "is_active": True,
    }
    defaults.update(overrides)
    provider = Provider(**defaults)  # type: ignore[arg-type]
    db_session.add(provider)
    return provider


async def _make_user(db_session) -> User:
    user = User(
        id=uuid4(),
        email=f"cost-test-{uuid4().hex[:6]}@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_model_config(
    db_session, *, provider_id, model_id, modality, cost_config=None, **overrides
) -> ModelConfig:
    data: dict = {
        "provider_id": provider_id,
        "model_id": model_id,
        "provider_model_id": f"provider-{model_id}",
        "display_name": model_id,
        "modality": modality,
        "endpoint_type": "comfyui",
        "cost_config": cost_config,
        "is_active": True,
    }
    data.update(overrides)
    config = await ModelConfigService.create(db_session, data)
    await db_session.flush()
    return config


async def _make_job(db_session, *, user_id, input_data) -> Job:
    job = Job(
        id=uuid4(),
        user_id=user_id,
        input_data=input_data,
    )
    db_session.add(job)
    await db_session.flush()
    return job


async def _make_scene(db_session, *, job_id, scene_number, start_time, end_time) -> VideoScene:
    scene = VideoScene(
        id=uuid4(),
        job_id=job_id,
        scene_number=scene_number,
        start_time=start_time,
        end_time=end_time,
    )
    db_session.add(scene)
    await db_session.flush()
    return scene


# ---------------------------------------------------------------------------
# estimate_media_call tests
# ---------------------------------------------------------------------------


class TestEstimateMediaCall:
    async def test_estimate_media_call_image(self):
        """Image cost uses cost_per_image multiplied by count."""
        provider_id = uuid4()
        config = ModelConfig(
            id=uuid4(),
            provider_id=provider_id,
            model_id="test-image-model",
            provider_model_id="provider-image",
            display_name="Test Image",
            modality="image",
            endpoint_type="comfyui",
            cost_config={"cost_per_image": Decimal("0.05"), "currency": "USD"},
        )

        item = estimate_media_call(config, "image", count=3)

        assert item.modality == "image"
        assert item.model_id == "test-image-model"
        assert item.provider_id == provider_id
        assert item.estimated_cost == Decimal("0.15")
        assert item.count == 3

    async def test_estimate_media_call_video(self):
        """Video cost uses cost_per_second multiplied by duration."""
        provider_id = uuid4()
        config = ModelConfig(
            id=uuid4(),
            provider_id=provider_id,
            model_id="test-video-model",
            provider_model_id="provider-video",
            display_name="Test Video",
            modality="video",
            endpoint_type="comfyui",
            cost_config={"cost_per_second": Decimal("0.02"), "currency": "USD"},
        )

        item = estimate_media_call(config, "video", duration=5, count=2)

        assert item.modality == "video"
        assert item.model_id == "test-video-model"
        assert item.estimated_cost == Decimal("0.20")
        assert item.duration_seconds == 5
        assert item.count == 2

    async def test_estimate_media_call_text(self):
        """Text cost uses token rates with fixed assumed token counts."""
        provider_id = uuid4()
        config = ModelConfig(
            id=uuid4(),
            provider_id=provider_id,
            model_id="test-text-model",
            provider_model_id="provider-text",
            display_name="Test Text",
            modality="text",
            endpoint_type="ollama",
            cost_config={
                "cost_per_1k_prompt_tokens": Decimal("0.01"),
                "cost_per_1k_completion_tokens": Decimal("0.02"),
                "currency": "USD",
            },
        )

        item = estimate_media_call(config, "text", count=2)

        # (0.01 * 4 + 0.02 * 2) * 2 = (0.04 + 0.04) * 2 = 0.16
        assert item.estimated_cost == Decimal("0.16")
        assert item.count == 2

    async def test_estimate_media_call_no_config_returns_zero(self):
        """A missing model config produces a zero-cost line item."""
        item = estimate_media_call(None, "image", count=5)

        assert item.estimated_cost == Decimal("0")
        assert item.model_id is None
        assert item.provider_id is None


# ---------------------------------------------------------------------------
# estimate_job_cost tests
# ---------------------------------------------------------------------------


class TestEstimateJobCost:
    async def test_estimate_job_cost_counts_subclips(self, db_session):
        """A scene longer than max_duration generates multiple video sub-clip items."""
        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-image",
            modality="image",
            cost_config={"cost_per_image": 0.05, "currency": "USD"},
        )
        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-video",
            modality="video",
            cost_config={"cost_per_second": 0.10, "currency": "USD"},
            constraints={"max_duration": 5},
        )
        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-text",
            modality="text",
            cost_config={
                "cost_per_1k_prompt_tokens": 0.01,
                "cost_per_1k_completion_tokens": 0.02,
                "currency": "USD",
            },
        )
        await db_session.commit()

        user = await _make_user(db_session)
        job = await _make_job(
            db_session,
            user_id=user.id,
            input_data={
                "image_model": "test-image",
                "video_model": "test-video",
                "text_model": "test-text",
            },
        )

        # 12-second scene => ceil(12 / 5) = 3 sub-clips
        scene = await _make_scene(
            db_session,
            job_id=job.id,
            scene_number=1,
            start_time=0,
            end_time=12,
        )
        await db_session.commit()

        estimate = await estimate_job_cost(db_session, job, [scene])

        assert isinstance(estimate, CostEstimate)
        assert estimate.currency == "USD"

        image_items = [i for i in estimate.items if i.modality == "image"]
        video_items = [i for i in estimate.items if i.modality == "video"]
        text_items = [i for i in estimate.items if i.modality == "text"]

        assert len(image_items) == 1
        assert image_items[0].estimated_cost == Decimal("0.05")

        # 12-second scene with max_duration=5 => three sub-clips: 5s, 5s, 2s
        assert len(video_items) == 3
        assert [item.duration_seconds for item in video_items] == [5, 5, 2]
        assert [item.count for item in video_items] == [1, 1, 1]
        assert sum(item.estimated_cost for item in video_items) == Decimal("1.20")

        assert len(text_items) == 1
        assert text_items[0].count == 2

        assert estimate.total == Decimal("0.05") + Decimal("1.20") + Decimal("0.16")

    async def test_estimate_job_cost_no_models_returns_zero(self, db_session):
        """A job with no selected models returns a zero-cost estimate."""
        user = await _make_user(db_session)
        job = await _make_job(db_session, user_id=user.id, input_data={})
        scene = await _make_scene(
            db_session,
            job_id=job.id,
            scene_number=1,
            start_time=0,
            end_time=5,
        )
        await db_session.commit()

        estimate = await estimate_job_cost(db_session, job, [scene])

        assert estimate.total == Decimal("0")
        assert estimate.items == []

    async def test_estimate_job_cost_uses_default_max_duration(self, db_session):
        """When video config has no max_duration constraint, default 5s is used."""
        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-video-default",
            modality="video",
            cost_config={"cost_per_second": 0.10, "currency": "USD"},
            constraints=None,
        )
        await db_session.commit()

        user = await _make_user(db_session)
        job = await _make_job(
            db_session,
            user_id=user.id,
            input_data={"video_model": "test-video-default"},
        )
        # 11-second scene => ceil(11 / 5) = 3 sub-clips
        scene = await _make_scene(
            db_session,
            job_id=job.id,
            scene_number=1,
            start_time=0,
            end_time=11,
        )
        await db_session.commit()

        estimate = await estimate_job_cost(db_session, job, [scene])

        # 11-second scene with default max_duration=5 => three sub-clips: 5s, 5s, 1s
        video_items = [i for i in estimate.items if i.modality == "video"]
        assert len(video_items) == 3
        assert [item.duration_seconds for item in video_items] == [5, 5, 1]
        assert sum(item.estimated_cost for item in video_items) == Decimal("1.10")

    async def test_estimate_job_cost_partial_subclip_priced_accurately(self, db_session):
        """Partial final sub-clip is charged only for its actual duration."""
        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-video-partial",
            modality="video",
            cost_config={"cost_per_second": 0.10, "currency": "USD"},
            constraints={"max_duration": 5},
        )
        await db_session.commit()

        user = await _make_user(db_session)
        job = await _make_job(
            db_session,
            user_id=user.id,
            input_data={"video_model": "test-video-partial"},
        )
        scene = await _make_scene(
            db_session,
            job_id=job.id,
            scene_number=1,
            start_time=0,
            end_time=11,
        )
        await db_session.commit()

        estimate = await estimate_job_cost(db_session, job, [scene])

        video_items = [i for i in estimate.items if i.modality == "video"]
        assert len(video_items) == 3
        assert video_items[0].estimated_cost == Decimal("0.50")
        assert video_items[1].estimated_cost == Decimal("0.50")
        assert video_items[2].estimated_cost == Decimal("0.10")
        assert sum(item.estimated_cost for item in video_items) == Decimal("1.10")

    async def test_estimate_job_cost_currency_from_first_configured_model(self, db_session):
        """Currency is taken from image config, then video, then text."""
        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-image-currency",
            modality="image",
            cost_config={"cost_per_image": 0.05, "currency": "EUR"},
        )
        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-video-currency",
            modality="video",
            cost_config={"cost_per_second": 0.10, "currency": "GBP"},
        )
        await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-text-currency",
            modality="text",
            cost_config={
                "cost_per_1k_prompt_tokens": 0.01,
                "cost_per_1k_completion_tokens": 0.02,
                "currency": "JPY",
            },
        )
        await db_session.commit()

        user = await _make_user(db_session)
        job = await _make_job(
            db_session,
            user_id=user.id,
            input_data={
                "image_model": "test-image-currency",
                "video_model": "test-video-currency",
                "text_model": "test-text-currency",
            },
        )
        scene = await _make_scene(
            db_session,
            job_id=job.id,
            scene_number=1,
            start_time=0,
            end_time=3,
        )
        await db_session.commit()

        estimate = await estimate_job_cost(db_session, job, [scene])

        assert estimate.currency == "EUR"


# ---------------------------------------------------------------------------
# Cost recording / actual cost tests
# ---------------------------------------------------------------------------


class TestRecordAndActualCost:
    async def test_record_media_generation_cost_creates_cost_log(self, db_session):
        """record_media_generation_cost inserts a CostLog row for the job."""
        provider = _make_provider(db_session=db_session)
        await db_session.flush()

        video_config = await _make_model_config(
            db_session,
            provider_id=provider.id,
            model_id="test-record-video",
            modality="video",
            cost_config={"cost_per_second": 0.10, "currency": "USD"},
        )
        await db_session.commit()

        user = await _make_user(db_session)
        job = await _make_job(db_session, user_id=user.id, input_data={})
        await db_session.commit()

        amount = await record_media_generation_cost(
            db_session, job, video_config, "video", duration=5
        )

        assert amount == Decimal("0.50")
        actual = await get_job_actual_cost(db_session, job.id)
        assert actual == Decimal("0.50")

    async def test_record_media_generation_cost_no_provider_is_noop(self, db_session):
        """When the model config has no provider, no CostLog is recorded."""
        config = ModelConfig(
            id=uuid4(),
            provider_id=None,
            model_id="orphan-model",
            provider_model_id="provider-orphan",
            display_name="Orphan",
            modality="image",
            endpoint_type="comfyui",
            cost_config={"cost_per_image": Decimal("0.05"), "currency": "USD"},
        )

        user = await _make_user(db_session)
        job = await _make_job(db_session, user_id=user.id, input_data={})
        await db_session.commit()

        amount = await record_media_generation_cost(db_session, job, config, "image")

        assert amount == Decimal("0.05")
        actual = await get_job_actual_cost(db_session, job.id)
        assert actual == Decimal("0")

    async def test_get_job_actual_cost_returns_zero_when_no_logs(self, db_session):
        """get_job_actual_cost returns 0 for a job with no CostLog rows."""
        user = await _make_user(db_session)
        job = await _make_job(db_session, user_id=user.id, input_data={})
        await db_session.commit()

        actual = await get_job_actual_cost(db_session, job.id)
        assert actual == Decimal("0")
