import json
import random
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import Job, Provider, UserSettings
from app.services.job_router import JobRouter
from app.services.model_config import get_default_model_preferences, get_model_config
from app.services.providers import (
    ComfyUIDirectProvider,
    PoeProvider,
    RunPodProvider,
)

settings = get_settings()


VIDEO_WORKFLOW_MAP: dict[str, str] = {
    "wan2.2_t2v": "wan_t2v.json",
    "wan2.2_s2v": "wan_s2v.json",
    "wan_t2v": "wan_t2v.json",
    "wan_s2v": "wan_s2v.json",
    "ltx2.3_t2v": "ltx_t2v.json",
    "ltx2.3_i2v": "ltx_i2v.json",
    "ltx_t2v": "ltx_t2v.json",
    "ltx_i2v": "ltx_i2v.json",
    "ltx_distilled": "ltx_distilled.json",
    "ltx2.3_distilled": "ltx_distilled.json",
}


async def get_provider_instance(
    db: AsyncSession,
    provider: Provider,
) -> PoeProvider | ComfyUIDirectProvider | RunPodProvider:
    if provider.provider_type == "poe":
        from app.services.providers import PoeProvider
        instance = PoeProvider(provider.id, provider.config)
        await instance.initialize(provider.config)
        return instance
    elif provider.provider_type == "comfyui_direct":
        from app.services.providers import ComfyUIDirectProvider
        instance = ComfyUIDirectProvider(provider.id, provider.config)
        await instance.initialize(provider.config)
        return instance
    elif provider.provider_type == "runpod":
        from app.services.providers import RunPodProvider
        instance = RunPodProvider(provider.id, provider.config)
        await instance.initialize(provider.config)
        return instance
    else:
        raise ValueError(f"Unknown provider type: {provider.provider_type}")


async def get_provider_for_job(
    db: AsyncSession,
    job: Job,
    modality: str,
) -> tuple[Provider | None, PoeProvider | ComfyUIDirectProvider | RunPodProvider | None]:
    provider_id = job.image_provider_id if modality == "image" else job.video_provider_id

    if provider_id:
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()
        if provider and provider.is_active:
            instance = await get_provider_instance(db, provider)
            return provider, instance
        return None, None

    router = JobRouter(db)
    candidates = []
    async for prov in router.iterate_providers():
        if modality == "image":
            if prov.provider_type == "comfyui_direct":
                candidates.append(prov)
        else:
            if prov.provider_type in ("comfyui_direct", "runpod", "poe"):
                candidates.append(prov)

    for candidate in candidates:
        try:
            instance = await get_provider_instance(db, candidate)
            return candidate, instance
        except Exception:
            continue

    return None, None


async def get_comfyui_direct_provider(
    db: AsyncSession,
    provider_id: UUID | None = None,
) -> tuple[Provider, ComfyUIDirectProvider]:
    provider: Provider | None = None

    if provider_id:
        result = await db.execute(
            select(Provider).where(
                Provider.id == provider_id,
                Provider.provider_type == "comfyui_direct",
                Provider.is_active == True,  # noqa: E712
            )
        )
        provider = result.scalar_one_or_none()

    if not provider:
        result = await db.execute(
            select(Provider).where(
                Provider.provider_type == "comfyui_direct",
                Provider.is_active == True,  # noqa: E712
            )
        )
        provider = result.scalar_one_or_none()

    if not provider:
        raise ValueError("No active ComfyUI Direct provider available.")

    instance = await get_provider_instance(db, provider)
    if not isinstance(instance, ComfyUIDirectProvider):
        raise ValueError(f"Expected ComfyUI Direct provider, got {provider.provider_type}")

    return provider, instance


async def get_user_model_preferences(db: AsyncSession, user_id: UUID) -> dict[str, str]:
    """Get user's model preferences from settings."""
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    user_settings = result.scalar_one_or_none()

    if not user_settings or not user_settings.preferences:
        return get_default_model_preferences()

    model_prefs = user_settings.preferences.get("models", {})
    if not model_prefs:
        return get_default_model_preferences()

    return {
        "image_model": model_prefs.get("image_model", "flux1-schnell"),
        "video_model": model_prefs.get("video_model", "wan2.2-t2v"),
        "image_provider": model_prefs.get("image_provider", "local"),
        "video_provider": model_prefs.get("video_provider", "local"),
    }


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


async def generate_image(
    db: AsyncSession,
    job: Job,
    prompt: str,
    scene_number: int,
    provider_id: UUID | None = None,
    model_preference: str | None = None,
    aspect_ratio: str = "3:2",
) -> tuple[str, str, UUID | None]:
    output_dir = get_scene_output_dir(str(job.id), scene_number)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / "seed_image.png"

    # Get user's model preferences
    user_prefs = await get_user_model_preferences(db, job.user_id)
    selected_model = model_preference or user_prefs.get("image_model", "sdxl")
    _ = get_model_config(selected_model)

    provider, instance = await get_comfyui_direct_provider(db, provider_id)

    # Use proper image workflow based on selected model
    if selected_model == "flux1-schnell":
        workflow = _build_flux_image_workflow(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            provider_config=instance.config,
        )
    else:
        # Fallback to existing workflow for other models
        workflow = _build_comfyui_image_workflow(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            model_preference=selected_model,
            provider_config=instance.config,
        )

    prompt_id = await instance.queue_prompt(workflow)
    result = await instance.wait_for_completion(prompt_id)

    # Get the image output
    image_data = await instance.get_output(result)
    if not image_data:
        raise ValueError("ComfyUI image generation returned no output data")

    image_path.write_bytes(image_data)

    if not image_path.exists():
        raise ValueError("Failed to save generated image")

    relative_path = str(image_path.relative_to(settings.storage_path))
    return relative_path, f"generated_with_{selected_model}", provider.id


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
) -> tuple[str, str, UUID | None, float]:
    output_dir = get_scene_output_dir(str(job.id), scene_number)
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / "scene_video.mp4"

    provider, instance = await get_comfyui_direct_provider(db, provider_id)

    # Build a proper Wan2.2 workflow with correct parameters
    workflow = _build_wan_video_workflow(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        frames=_duration_to_frames(duration),
        provider_config=instance.config,
    )

    prompt_id = await instance.queue_prompt(workflow)
    result = await instance.wait_for_completion(prompt_id)
    output_data = await instance.get_output(result)
    if output_data:
        video_path.write_bytes(output_data)
    else:
        raise ValueError("ComfyUI returned no output data")
    return (
        str(video_path.relative_to(settings.storage_path)),
        f"generated_with_{model_preference or 'wan'}",
        provider.id,
        float(duration),
    )


def _build_wan_video_workflow(
    prompt: str,
    aspect_ratio: str,
    frames: int,
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    """Build a Wan2.2 video generation workflow.

    Uses the image-to-video (ti2v) model by default, which produces
    higher quality than text-to-video.
    """
    width, height = _video_generation_resolution(aspect_ratio)
    seed = random.randint(0, 2**31 - 1)

    clip_name = str(provider_config.get("wan_clip_name") or "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
    vae_name = str(provider_config.get("wan_vae_name") or "wan2.2_vae.safetensors")
    unet_name = str(provider_config.get("wan_unet_name") or "wan2.2_ti2v_5B_fp16.safetensors")

    # Quality settings — these are the sweet spot for Wan2.2
    steps = int(provider_config.get("wan_video_steps") or 30)
    cfg = float(provider_config.get("wan_video_cfg") or 5.0)
    shift = float(provider_config.get("wan_video_shift") or 8.0)
    fps = int(provider_config.get("wan_video_fps") or 16)
    sampler = str(provider_config.get("wan_video_sampler") or "uni_pc")
    scheduler = str(provider_config.get("wan_video_scheduler") or "simple")
    negative_prompt = str(provider_config.get("wan_video_negative_prompt") or "")

    return {
        "1": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip_name, "type": "wan"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 0]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["1", 0]},
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
        },
        "5": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "6": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["5", 0], "shift": shift},
        },
        "7": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {"width": width, "height": height, "length": frames, "batch_size": 1},
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
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["8", 0], "vae": ["4", 0]},
        },
        "10": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["9", 0], "fps": fps},
        },
        "11": {
            "class_type": "SaveVideo",
            "inputs": {"video": ["10", 0], "filename_prefix": "vidforge", "format": "mp4", "codec": "h264"},
        },
    }


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
        provider_config.get("image_scheduler") or provider_config.get("wan_image_scheduler") or "simple"
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


def _next_workflow_node_id(workflow: dict[str, Any]) -> str:
    numeric_ids = [int(node_id) for node_id in workflow if node_id.isdigit()]
    if not numeric_ids:
        return "1"
    return str(max(numeric_ids) + 1)


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


def _duration_to_frames(duration: int, fps: int = 16) -> int:
    """Convert duration in seconds to frame count.

    Wan2.2 works well with 16fps.  Frame count is always odd (>= 9)
    as required by EmptyHunyuanLatentVideo.
    """
    frames = int(duration * fps)
    if frames < 9:
        frames = 9
    if frames % 2 == 0:
        frames += 1
    return frames


def _video_generation_resolution(aspect_ratio: str) -> tuple[int, int]:
    """Resolution for video generation.

    Uses 848x480 (or equivalent) which is the sweet spot for Wan2.2
    on consumer GPUs — large enough for good quality, small enough
    to fit in VRAM at 30 steps with 80+ frames.
    """
    ratios = {
        "16:9": (848, 480),
        "9:16": (480, 848),
        "1:1": (640, 640),
        "4:3": (640, 480),
        "3:2": (640, 432),
        "21:9": (848, 384),
    }
    return ratios.get(aspect_ratio, (848, 480))


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

    unet_name = str(
        provider_config.get("flux_unet_name")
        or "flux1-schnell-fp8.safetensors"
    )
    clip_name1 = str(
        provider_config.get("flux_clip_name1") or "clip_l.safetensors"
    )
    clip_name2 = str(
        provider_config.get("flux_clip_name2") or "t5xxl_fp8_e4m3fn.safetensors"
    )
    vae_name = str(
        provider_config.get("flux_vae_name") or "ae.safetensors"
    )

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
