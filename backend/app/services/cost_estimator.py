from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import CostLog, Job, ModelConfig, VideoScene
from app.services.budget_tracker import BudgetTracker
from app.services.model_config_service import ModelConfigService
from app.services.model_metadata import get_model_constraint

DEFAULT_CURRENCY = "USD"
MIN_SCENE_DURATION_SECONDS = 2
TEXT_PLANNING_CALL_COUNT = 2
ASSUMED_PROMPT_1K_TOKENS = 4
ASSUMED_COMPLETION_1K_TOKENS = 2
DEFAULT_MAX_CLIP_DURATION = 5


@dataclass
class CostLineItem:
    label: str
    modality: str
    provider_id: UUID | None
    model_id: str | None
    estimated_cost: Decimal
    duration_seconds: float | None = None
    count: int = 1


@dataclass
class CostEstimate:
    total: Decimal
    currency: str
    items: list[CostLineItem] = field(default_factory=list)


def _as_decimal(value: float | int | Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def estimate_media_call(
    model_config: ModelConfig | None,
    modality: str,
    duration: float | None = None,
    count: int = 1,
) -> CostLineItem:
    cc = model_config.cost_config if model_config else None
    cc = cc or {}

    if modality == "image":
        cost = _as_decimal(cc.get("cost_per_image")) * count
    elif modality == "video":
        cost = _as_decimal(cc.get("cost_per_second")) * _as_decimal(duration or 0) * count
    elif modality == "text":
        # rough planning/call cost; actual token counts are unknown before generation
        prompt_cost = _as_decimal(cc.get("cost_per_1k_prompt_tokens")) * Decimal(
            str(ASSUMED_PROMPT_1K_TOKENS)
        )
        completion_cost = _as_decimal(cc.get("cost_per_1k_completion_tokens")) * Decimal(
            str(ASSUMED_COMPLETION_1K_TOKENS)
        )
        cost = (prompt_cost + completion_cost) * count
    else:
        cost = Decimal("0")

    return CostLineItem(
        label=f"{modality} generation ({model_config.model_id if model_config else 'unknown'})",
        modality=modality,
        provider_id=model_config.provider_id if model_config else None,
        model_id=model_config.model_id if model_config else None,
        estimated_cost=cost,
        duration_seconds=duration,
        count=count,
    )


async def estimate_job_cost(
    db: AsyncSession,
    job: Job,
    scenes: list[VideoScene],
    context: dict[str, Any] | None = None,
) -> CostEstimate:
    """Estimate the total cost of a scene-based job from selected models."""
    input_data = job.input_data or {}
    image_model_id = input_data.get("image_model")
    video_model_id = input_data.get("video_model")
    text_model_id = input_data.get("text_model")

    image_config = None
    if image_model_id:
        image_config = await ModelConfigService.resolve_model_config(db, image_model_id)

    video_config = None
    if video_model_id:
        video_config = await ModelConfigService.resolve_model_config(db, video_model_id)

    text_config = None
    if text_model_id:
        text_config = await ModelConfigService.resolve_model_config(db, text_model_id)

    max_clip_duration = get_model_constraint(
        {"constraints": video_config.constraints if video_config else None},
        "max_duration",
        DEFAULT_MAX_CLIP_DURATION,
    )

    items: list[CostLineItem] = []

    # one seed image per scene
    if image_config:
        items.append(estimate_media_call(image_config, "image", count=len(scenes)))

    # video sub-clips per scene
    if video_config:
        for scene in scenes:
            scene_duration = max(MIN_SCENE_DURATION_SECONDS, scene.end_time - scene.start_time)
            num_subclips = max(1, math.ceil(scene_duration / max_clip_duration))
            for i in range(num_subclips):
                if i < num_subclips - 1:
                    duration = max_clip_duration
                else:
                    duration = scene_duration - (num_subclips - 1) * max_clip_duration
                items.append(
                    estimate_media_call(
                        video_config,
                        "video",
                        duration=duration,
                        count=1,
                    )
                )

    # LLM planning calls (scene plan + sub-scene prompt decomposition fallback)
    if text_config:
        items.append(
            estimate_media_call(text_config, "text", count=TEXT_PLANNING_CALL_COUNT)
        )

    currency = DEFAULT_CURRENCY
    for config in (image_config, video_config, text_config):
        if config and config.cost_config:
            currency = config.cost_config.get("currency", currency)
            break

    total = sum((item.estimated_cost for item in items), Decimal("0"))
    return CostEstimate(total=total, currency=currency, items=items)


async def record_media_generation_cost(
    db: AsyncSession,
    job: Job,
    model_config: ModelConfig | None,
    modality: str,
    duration: float | None = None,
) -> Decimal:
    """Record a single CostLog row for a successful media generation call."""
    item = estimate_media_call(model_config, modality, duration=duration, count=1)
    if item.estimated_cost <= 0 or not item.provider_id:
        return item.estimated_cost

    tracker = BudgetTracker(db)
    await tracker.record_spend(
        provider_id=item.provider_id,
        job_id=job.id,
        amount=item.estimated_cost,
        duration_seconds=int(duration or 0) if modality == "video" else None,
        gpu_type=None,
    )
    return item.estimated_cost


async def get_job_actual_cost(db: AsyncSession, job_id: UUID) -> Decimal:
    from sqlalchemy import func, select

    result = await db.execute(
        select(func.coalesce(func.sum(CostLog.amount), Decimal("0"))).where(
            CostLog.job_id == job_id
        )
    )
    return result.scalar_one()
