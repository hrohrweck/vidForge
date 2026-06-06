import json
import logging
import random
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import ErrorOrigin, ErrorSeverity, Job, ModelConfig, Provider, UserSettings
from app.services.error_capture import log_user_error
from app.services.job_router import JobRouter
from app.services.model_config_service import ModelConfigService
from app.services.providers import registry
from app.services.providers.base import (
    ImageProvider,
    ProviderConnectionError,
    ProviderError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    VideoProvider,
)
from app.services.video_processor import (
    InvalidVideoOutputError,
    ValidationResult,  # noqa: F401
    VideoProcessor,
)

settings = get_settings()
logger = logging.getLogger(__name__)

def _sanitize_filename(name: str, ext: str) -> str:
    """Sanitize a name for use as a filename."""
    import re

    sanitized = re.sub(r"[^\w\s-]", "", name).strip()
    sanitized = re.sub(r"[-\s]+", "_", sanitized)
    return (sanitized[:50] or "untitled") + ext


def _map_media_error_to_friendly_message(exc: Exception, modality: str) -> str:
    """Map media generation exceptions to user-friendly messages.

    Uses ProviderError sub-types for classification, eliminating
    provider-specific string matching.
    """
    if isinstance(exc, InvalidVideoOutputError):
        return (
            f"Generated video failed validation "
            f"({exc.result.actual_frames} frames, expected {exc.result.expected_frames})"
        )

    if isinstance(exc, ProviderOverloadedError):
        return "AI service is busy, please try again later"

    if isinstance(exc, ProviderRateLimitError):
        return "Too many requests, please try again later"

    if isinstance(exc, ProviderConnectionError):
        return "Connection failed, please check your network"

    if isinstance(exc, ProviderTimeoutError):
        return "Request timed out, please try again later"

    if isinstance(exc, ProviderError):
        return f"{'Image' if modality == 'image' else 'Video'} generation service error, please try again"

    # Legacy string-based fallback for unclassified exceptions
    exc_msg = str(exc).lower()

    # Overloaded
    if "overloaded" in exc_msg or "capacity" in exc_msg or "queue is full" in exc_msg:
        return "AI service is busy, please try again later"

    # Rate limiting
    if "rate limit" in exc_msg or "429" in exc_msg:
        return "Too many requests, please try again later"

    # Connection errors
    if "connection" in exc_msg or "connectionerror" in exc_msg:
        return "Connection failed, please check your network"

    # Timeout errors
    if "timeout" in exc_msg or "timed out" in exc_msg:
        return "Request timed out, please try again later"

    # No data returned
    if "no data" in exc_msg or "no output" in exc_msg:
        return f"{'Image' if modality == 'image' else 'Video'} generation returned no data, please try again"

    # Generic fallback
    return "An error occurred, please try again"


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

            details = {
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


async def get_provider_instance(
    db: AsyncSession,
    provider: Provider,
) -> Any:
    """Create and initialize a provider instance via the registry.

    Thin wrapper around ``registry.create()``.  Kept as a public function
    for backward compatibility with existing callers and test mocking.
    """
    return await registry.create(provider.provider_type, provider.id, provider.config)


async def get_provider_for_job(
    db: AsyncSession,
    job: Job,
    modality: str,
) -> tuple[Provider | None, Any]:
    """Resolve an active provider instance for the given job and modality.

    Uses registry-based lookup — no longer hard-codes provider-type lists.
    Falls back to iterating all capable providers via JobRouter.
    """
    provider_id = job.image_provider_id if modality == "image" else job.video_provider_id

    if provider_id:
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()
        if provider and provider.is_active:
            instance = await registry.create(
                provider.provider_type, provider.id, provider.config
            )
            return provider, instance
        return None, None

    router = JobRouter(db)
    async for prov in router.iterate_providers():
        try:
            instance = await registry.create(
                prov.provider_type, prov.id, prov.config
            )
            # get_capabilities() is on ProviderBase — runtime instances
            # have it even though registry.create() returns ComfyUIProvider.
            caps = instance.get_capabilities()  # type: ignore[attr-defined]
            if modality == "image" and caps.supports_image:
                return prov, instance
            if modality == "video" and caps.supports_video:
                return prov, instance
        except Exception:
            continue

    return None, None


async def get_user_model_preferences(db: AsyncSession, user_id: UUID) -> dict[str, str]:
    """Get user's full model preferences from settings.

    Returns all granular and coarse model fields plus provider_id companions.
    Falls back to defaults for any missing fields.
    """
    from app.api.models import get_default_model_preferences

    defaults = await get_default_model_preferences(db)

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    user_settings = result.scalar_one_or_none()

    if not user_settings or not user_settings.preferences:
        return defaults

    model_prefs = user_settings.preferences.get("models", {})
    if not model_prefs:
        return defaults

    # Merge stored prefs over defaults, preserving all fields
    merged = dict(defaults)
    for key in defaults:
        if key in model_prefs:
            merged[key] = model_prefs[key]
    return merged


def select_model_for(prefs: dict[str, str], task: str) -> tuple[str, str]:
    """Select the appropriate model_id and provider_id for a given task.

    Args:
        prefs: Full preferences dict from get_user_model_preferences().
        task: One of "text_to_image", "image_to_image", "text_to_video",
              "image_to_video", "text".

    Returns:
        (model_id, provider_id) tuple. Falls back to coarse fields when
        granular fields are empty.
    """
    if task == "image_to_video":
        model = prefs.get("image_to_video_model", "")
        provider = prefs.get("image_to_video_provider_id", "")
        if model:
            return model, provider
        return prefs.get("video_model", "wan2.2"), prefs.get("video_provider_id", "")

    if task == "text_to_video":
        model = prefs.get("text_to_video_model", "")
        provider = prefs.get("text_to_video_provider_id", "")
        if model:
            return model, provider
        return prefs.get("video_model", "wan2.2"), prefs.get("video_provider_id", "")

    if task == "image_to_image":
        model = prefs.get("image_to_image_model", "")
        provider = prefs.get("image_to_image_provider_id", "")
        if model:
            return model, provider
        return prefs.get("image_model", "flux1-schnell"), prefs.get("image_provider_id", "")

    if task == "text_to_image":
        model = prefs.get("text_to_image_model", "")
        provider = prefs.get("text_to_image_provider_id", "")
        if model:
            return model, provider
        return prefs.get("image_model", "flux1-schnell"), prefs.get("image_provider_id", "")

    if task == "text":
        return prefs.get("text_model", "qwen3.6:35b"), prefs.get("text_provider_id", "")

    raise ValueError(f"Unknown task: {task}")


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


def get_comfyui_workflow_path(workflow_name: str) -> Path | None:
    search_paths = [
        Path(settings.comfyui_workflows_path) / workflow_name,
        Path(settings.storage_path).parent / "workflows" / workflow_name,
        Path(__file__).parent.parent / "comfyui" / "workflows" / workflow_name,
        Path(__file__).parent.parent.parent / "templates" / "workflows" / workflow_name,
    ]
    for workflow_path in search_paths:
        if workflow_path.exists():
            return workflow_path
    return None


def load_comfyui_workflow(workflow_name: str) -> dict[str, Any] | None:
    workflow_path = get_comfyui_workflow_path(workflow_name)
    if not workflow_path:
        return None
    return json.loads(workflow_path.read_text())


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
            instance = await registry.create(
                provider.provider_type, provider.id, provider.config
            )
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
    instance = await registry.create(
        provider.provider_type, provider.id, provider.config
    )
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
            instance = await registry.create(
                provider.provider_type, provider.id, provider.config
            )
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
    instance = await registry.create(
        provider.provider_type, provider.id, provider.config
    )
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
    except Exception as exc:
        classified = instance.classify_error(exc)
        import asyncio
        asyncio.create_task(
            _capture_media_error(
                job, classified, "image", model=selected_model, provider=str(resolved_pid)
            )
        )
        raise

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
        import asyncio
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
    except InvalidVideoOutputError:
        Path(tmp_path).unlink(missing_ok=True)
        raise
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
def _build_comfyui_image_workflow(
    prompt: str,
    aspect_ratio: str,
    model_preference: str | None,
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    width, height = _aspect_ratio_to_dimensions(aspect_ratio)
    seed = random.randint(0, 2**31 - 1)

    clip_name = str(
        provider_config.get("wan_clip_name")
        or provider_config.get("image_clip_name")
        or "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    )
    vae_name = str(
        provider_config.get("wan_vae_name")
        or provider_config.get("image_vae_name")
        or "wan2.2_vae.safetensors"
    )
    unet_name = _select_wan_image_unet(model_preference, provider_config)

    negative_prompt = str(
        provider_config.get("image_negative_prompt")
        or provider_config.get("wan_image_negative_prompt")
        or ""
    )
    steps = int(provider_config.get("image_steps") or provider_config.get("wan_image_steps") or 30)
    cfg = float(provider_config.get("image_cfg") or provider_config.get("wan_image_cfg") or 5.0)
    sampler_name = str(
        provider_config.get("image_sampler") or provider_config.get("wan_image_sampler") or "uni_pc"
    )
    scheduler = str(
        provider_config.get("image_scheduler")
        or provider_config.get("wan_image_scheduler")
        or "simple"
    )
    shift = float(provider_config.get("wan_image_shift") or 8.0)

    # Wan2.2 is a video-family model.  ComfyUI's Wan pipeline expects the Hunyuan/Wan
    # video latent shape, even when only one still is requested.  A length of 1 creates
    # a single decoded frame, which SaveImage can persist directly as a static image.
    return {
        "1": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": clip_name,
                "type": "wan",
            },
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["1", 0],
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["1", 0],
            },
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": vae_name,
            },
        },
        "5": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": str(provider_config.get("wan_unet_weight_dtype") or "default"),
            },
        },
        "6": {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": ["5", 0],
                "shift": shift,
            },
        },
        "7": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {
                "width": width,
                "height": height,
                "length": 1,
                "batch_size": 1,
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["6", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["7", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["4", 0],
            },
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": "vidforge_seed_image",
            },
        },
    }


def _select_wan_image_unet(
    model_preference: str | None,
    provider_config: dict[str, Any],
) -> str:
    configured_unet = (
        provider_config.get("wan_image_unet_name")
        or provider_config.get("image_unet_name")
        or provider_config.get("wan_unet_name")
    )
    if configured_unet:
        return str(configured_unet)

    normalized_model = (model_preference or "").lower()
    if "it2v" in normalized_model:
        return "wan2.2_it2v_5B_fp16.safetensors"

    return "wan2.2_ti2v_5B_fp16.safetensors"


def _aspect_ratio_to_dimensions(aspect_ratio: str) -> tuple[int, int]:
    ratios = {
        "16:9": (1280, 720),
        "9:16": (720, 1280),
        "1:1": (1024, 1024),
        "4:3": (1024, 768),
        "3:2": (1152, 768),
        "21:9": (1680, 720),
    }
    return ratios.get(aspect_ratio, (1280, 720))


def _build_flux_image_workflow(
    prompt: str,
    aspect_ratio: str,
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    """Build a Flux image generation workflow using UNETLoader.

    Uses UNETLoader + DualCLIPLoader + VAELoader instead of
    CheckpointLoaderSimple because the flux checkpoint may not
    be registered in ComfyUI's checkpoints directory.
    """
    width, height = _aspect_ratio_to_dimensions(aspect_ratio)
    seed = random.randint(0, 2**31 - 1)

    unet_name = str(provider_config.get("flux_unet_name") or "flux1-schnell-fp8.safetensors")
    clip_name1 = str(provider_config.get("flux_clip_name1") or "clip_l.safetensors")
    clip_name2 = str(provider_config.get("flux_clip_name2") or "t5xxl_fp8_e4m3fn.safetensors")
    vae_name = str(provider_config.get("flux_vae_name") or "ae.safetensors")

    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": clip_name1,
                "clip_name2": clip_name2,
                "type": "flux",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": vae_name,
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "",
                "clip": ["2", 0],
            },
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["3", 0],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "vidforge_flux_image",
            },
        },
    }
