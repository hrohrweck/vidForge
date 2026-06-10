import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import ErrorOrigin, ErrorSeverity, Job, ModelConfig
from app.services.comfyui_workflows import (
    _aspect_ratio_to_dimensions,
    _build_comfyui_image_workflow,
    _build_flux_image_workflow,
    _select_wan_image_unet,
    get_comfyui_workflow_path,
    load_comfyui_workflow,
)
from app.services.error_capture import log_user_error
from app.services.error_mapping import classify_provider_error
from app.services.model_config_service import ModelConfigService
from app.services.model_resolution import (
    get_provider_for_job,
    get_provider_instance,
    get_user_model_preferences,
    select_model_for,
)
from app.services.providers.base import (
    ImageProvider,
    VideoProvider,
)
from app.services.video_processor import (
    InvalidVideoOutputError,
    ValidationResult,  # noqa: F401
    VideoProcessor,
)

settings = get_settings()
logger = logging.getLogger(__name__)

__all__ = [
    "ValidationResult",
    "_aspect_ratio_to_dimensions",
    "_build_comfyui_image_workflow",
    "_build_flux_image_workflow",
    "_select_wan_image_unet",
    "enforce_min_scene_duration",
    "generate_image",
    "generate_video",
    "get_comfyui_workflow_path",
    "get_provider_for_job",
    "get_provider_instance",
    "get_scene_output_dir",
    "get_user_model_preferences",
    "load_comfyui_workflow",
    "select_model_for",
]


def _sanitize_filename(name: str, ext: str) -> str:
    """Sanitize a name for use as a filename."""
    import re

    sanitized = re.sub(r"[^\w\s-]", "", name).strip()
    sanitized = re.sub(r"[-\s]+", "_", sanitized)
    return (sanitized[:50] or "untitled") + ext


def _map_media_error_to_friendly_message(exc: Exception, modality: str) -> str:
    classified = classify_provider_error(exc)
    if classified.category == "provider":
        return f"{'Image' if modality == 'image' else 'Video'} generation service error, please try again"
    if classified.category == "no_data":
        return f"{'Image' if modality == 'image' else 'Video'} generation returned no data, please try again"
    return classified.message


async def _capture_media_error(
    job: "Job",
    exc: Exception,
    modality: str,
    **extra_context,
) -> None:
    """Capture media generation error for notification system (fire-and-forget)."""
    try:
        from app.services.error_capture import log_user_error
        from app.workers.context import ctx

        async with ctx.session_factory() as db:
            # Refresh job to get user_id
            from sqlalchemy import select

            result = await db.execute(select(Job).where(Job.id == job.id))
            fresh_job = result.scalar_one_or_none()
            user_id = fresh_job.user_id if fresh_job else job.user_id

            if not user_id:
                return

            details: dict[str, Any] = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "modality": modality,
            }
            if isinstance(exc, InvalidVideoOutputError):
                details["actual_frames"] = exc.result.actual_frames
                details["expected_frames"] = exc.result.expected_frames
                details["actual_duration"] = exc.result.actual_duration
            details.update(extra_context)

            await log_user_error(
                db,
                user_id=user_id,
                severity=ErrorSeverity.ERROR,
                origin=ErrorOrigin.MEDIA_GENERATION
                if modality == "image"
                else ErrorOrigin.VIDEO_GENERATION,
                message=_map_media_error_to_friendly_message(exc, modality),
                details=details,
                source_id=job.id,
                source_type="job",
            )
    except Exception:
        pass  # Silent failure - don't block media generation


async def check_aspect_ratio_support(
    model_config: ModelConfig,
    requested_aspect: str,
) -> tuple[bool, str | None]:
    """
    Check whether a model supports a requested aspect ratio.

    Reads ``model_config.constraints['supported_aspect_ratios']`` (if present) and
    returns whether ``requested_aspect`` is allowed. A missing constraints dict or
    a missing/empty ``supported_aspect_ratios`` list means the model is treated
    as fully permissive.

    Args:
        model_config: The ModelConfig row describing the candidate model.
        requested_aspect: Aspect ratio string requested by the caller, e.g.
            ``"16:9"`` or ``"9:16"``.

    Returns:
        A ``(is_supported, warning_message)`` tuple. ``warning_message`` is
        ``None`` when the aspect ratio is supported; otherwise it is a
        user-friendly string describing the supported ratios and noting that
        the output will be letterboxed/pillarboxed to match the request.
    """
    constraints = model_config.constraints or {}
    supported = constraints.get("supported_aspect_ratios")

    if not supported:
        return True, None

    if requested_aspect in supported:
        return True, None

    supported_str = ", ".join(supported)
    display_name = model_config.display_name
    warning = (
        f"Model '{display_name}' only supports {supported_str}. "
        f"The output will be converted to {requested_aspect} with black bars."
    )
    return False, warning




MIN_SCENE_DURATION = 2.0  # Minimum scene duration in seconds


def enforce_min_scene_duration(
    scenes: list[dict[str, Any]],
    min_duration: float = MIN_SCENE_DURATION,
) -> list[dict[str, Any]]:
    """Merge scenes shorter than min_duration into the previous scene.

    If the first scene is too short, merge into the next. If only one
    scene exists, extend it to min_duration.
    """
    if not scenes:
        return scenes

    merged: list[dict[str, Any]] = []
    for scene in scenes:
        duration = scene.get("end_time", 0) - scene.get("start_time", 0)
        if duration < min_duration and merged:
            # Too short — merge into previous scene
            merged[-1]["end_time"] = scene.get("end_time", merged[-1]["end_time"])
            # Combine descriptions
            if scene.get("visual_description"):
                prev = merged[-1].get("visual_description", "")
                merged[-1]["visual_description"] = f"{prev}; {scene['visual_description']}".strip(
                    "; "
                )
            if scene.get("image_prompt") and not merged[-1].get("image_prompt"):
                merged[-1]["image_prompt"] = scene["image_prompt"]
            if scene.get("lyrics_segment") and not merged[-1].get("lyrics_segment"):
                merged[-1]["lyrics_segment"] = scene["lyrics_segment"]
            if scene.get("narration") and not merged[-1].get("narration"):
                merged[-1]["narration"] = scene["narration"]
        else:
            merged.append(scene)

    # Handle single remaining scene that's still too short
    if len(merged) == 1:
        dur = merged[0].get("end_time", 0) - merged[0].get("start_time", 0)
        if dur < min_duration:
            merged[0]["end_time"] = merged[0]["start_time"] + min_duration

    # Re-number
    for i, scene in enumerate(merged):
        scene["scene_number"] = i + 1

    return merged


def get_scene_output_dir(job_id: str, scene_number: int) -> Path:
    return Path(settings.storage_path) / "output" / job_id / f"scene_{scene_number:03d}"


async def _resolve_image_provider(
    db: AsyncSession,
    job: Job,
    provider_id: UUID | None,
    model_preference: str | None,
    has_reference_image: bool = False,
) -> tuple[str, UUID | None, Any]:
    """Resolve which provider and model to use for image generation.

    Returns (selected_model_id, resolved_provider_id, provider_instance).
    """

    # Fallback: read provider_id from job input_data if not passed explicitly
    if provider_id is None and job.input_data:
        pid_str = job.input_data.get("image_provider_id")
        if pid_str:
            try:
                provider_id = UUID(pid_str)
            except ValueError:
                pass

    if model_preference:
        config = await ModelConfigService.resolve_model_config(db, model_preference, provider_id)
        if config:
            provider = config.provider
            instance = await get_provider_instance(db, provider)
            return config.model_id, provider.id, instance

    user_prefs = await get_user_model_preferences(db, job.user_id)
    task = "image_to_image" if has_reference_image else "text_to_image"
    model_id, provider_id_str = select_model_for(user_prefs, task)

    if provider_id_str:
        provider_id = UUID(provider_id_str)

    config = await ModelConfigService.resolve_model_config(db, model_id, provider_id)
    if not config:
        raise ValueError(f"Could not resolve image model: {model_id} (provider_id={provider_id})")

    provider = config.provider
    instance = await get_provider_instance(db, provider)
    return config.model_id, provider.id, instance


async def _resolve_video_provider(
    db: AsyncSession,
    job: Job,
    provider_id: UUID | None,
    model_preference: str | None,
    has_seed_image: bool = False,
) -> tuple[str, UUID | None, Any]:
    """Resolve which provider and model to use for video generation.

    Returns (selected_model_id, resolved_provider_id, provider_instance).
    """

    # Fallback: read provider_id from job input_data if not passed explicitly
    if provider_id is None and job.input_data:
        pid_str = job.input_data.get("video_provider_id")
        if pid_str:
            try:
                provider_id = UUID(pid_str)
            except ValueError:
                pass

    if model_preference:
        config = await ModelConfigService.resolve_model_config(db, model_preference, provider_id)
        if config:
            provider = config.provider
            instance = await get_provider_instance(db, provider)
            return config.model_id, provider.id, instance

    user_prefs = await get_user_model_preferences(db, job.user_id)
    task = "image_to_video" if has_seed_image else "text_to_video"
    model_id, provider_id_str = select_model_for(user_prefs, task)

    if provider_id_str:
        provider_id = UUID(provider_id_str)

    config = await ModelConfigService.resolve_model_config(db, model_id, provider_id)
    if not config:
        raise ValueError(f"Could not resolve video model: {model_id} (provider_id={provider_id})")

    provider = config.provider
    instance = await get_provider_instance(db, provider)
    return config.model_id, provider.id, instance


async def generate_image(
    db: AsyncSession,
    job: Job,
    prompt: str,
    scene_number: int,
    provider_id: UUID | None = None,
    model_preference: str | None = None,
    aspect_ratio: str = "3:2",
    reference_image_path: str | None = None,
    reference_image_strength: float = 0.75,
    lora_path: str | None = None,
    lora_strength: float = 0.8,
    title: str | None = None,
) -> tuple[str, str, UUID | None]:
    output_dir = get_scene_output_dir(str(job.id), scene_number)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename_base = (
        _sanitize_filename(title or prompt[:50], ".png") if title or prompt else "seed_image.png"
    )
    image_path = output_dir / filename_base

    selected_model, resolved_pid, instance = await _resolve_image_provider(
        db,
        job,
        provider_id,
        model_preference,
        has_reference_image=bool(reference_image_path),
    )

    if not isinstance(instance, ImageProvider):
        raise ValueError(
            f"Provider {getattr(instance, 'provider_id', 'unknown')} "
            f"does not support image generation"
        )

    image_data: bytes | None = None
    max_retries = 4
    base_delay = 10.0
    for attempt in range(max_retries + 1):
        try:
            _asset_id, image_data = await instance.generate_image(
                prompt=prompt,
                model=selected_model,
                aspect_ratio=aspect_ratio,
                image_path=reference_image_path,
                reference_image_strength=reference_image_strength,
                lora_path=lora_path,
                lora_strength=lora_strength,
            )
            break
        except Exception as exc:
            classified = instance.classify_error(exc)
            mapped = classify_provider_error(classified)
            if not mapped.recoverable or attempt >= max_retries:
                asyncio.create_task(
                    _capture_media_error(
                        job, classified, "image", model=selected_model, provider=str(resolved_pid)
                    )
                )
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "[image_generation] Attempt %d/%d failed (recoverable): %s — "
                "retrying in %.0fs",
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    if not image_data:
        raise ValueError(f"Image generation returned no data (model={selected_model})")

    image_path.write_bytes(image_data)
    relative_path = str(image_path.relative_to(settings.storage_path))
    return relative_path, f"generated_with_{selected_model}", resolved_pid


async def generate_video(
    db: AsyncSession,
    job: Job,
    prompt: str,
    scene_number: int,
    reference_image_path: str | None = None,
    provider_id: UUID | None = None,
    model_preference: str | None = None,
    duration: int = 5,
    aspect_ratio: str = "16:9",
    title: str | None = None,
) -> tuple[str, str, UUID | None, float, str | None]:
    output_dir = get_scene_output_dir(str(job.id), scene_number)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename_base = (
        _sanitize_filename(title or prompt[:50], ".mp4") if title or prompt else "scene_video.mp4"
    )
    video_path = output_dir / filename_base

    selected_model, resolved_pid, instance = await _resolve_video_provider(
        db,
        job,
        provider_id,
        model_preference,
        has_seed_image=bool(reference_image_path),
    )

    if not isinstance(instance, VideoProvider):
        raise ValueError(
            f"Provider {getattr(instance, 'provider_id', 'unknown')} "
            f"does not support video generation"
        )

    # Check aspect ratio support
    ar_warning: str | None = None
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.model_id == selected_model,
            ModelConfig.is_active == True,  # noqa: E712
        )
    )
    model_info = result.scalars().first()
    if model_info:
        _supported, ar_warning = await check_aspect_ratio_support(model_info, aspect_ratio)
        if ar_warning:
            await log_user_error(
                db,
                user_id=job.user_id,
                severity=ErrorSeverity.WARNING,
                origin=ErrorOrigin.VIDEO_GENERATION,
                message=ar_warning,
                details={
                    "scene_number": scene_number,
                    "model": selected_model,
                    "requested_aspect_ratio": aspect_ratio,
                },
                source_id=job.id,
                source_type="job",
            )

    try:
        _asset_id, output_data = await instance.generate_video(
            prompt=prompt,
            model=selected_model,
            duration=duration,
            aspect_ratio=aspect_ratio,
            image_path=reference_image_path,
        )
    except Exception as exc:
        classified = instance.classify_error(exc)
        asyncio.create_task(
            _capture_media_error(
                job, classified, "video", model=selected_model, provider=str(resolved_pid)
            )
        )
        raise

    if not output_data:
        raise ValueError(f"Video generation returned no data (model={selected_model})")

    # Validate video output
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(output_data)
        tmp_path = tmp.name

    try:
        validation_result = await VideoProcessor.validate_video_output(
            tmp_path,
            expected_duration=float(duration),
            fps=16.0,
        )
        if not validation_result.valid:
            raise InvalidVideoOutputError(tmp_path, validation_result)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    video_path.write_bytes(output_data)
    return (
        str(video_path.relative_to(settings.storage_path)),
        f"generated_with_{selected_model}",
        resolved_pid,
        float(duration),
        ar_warning,
    )
