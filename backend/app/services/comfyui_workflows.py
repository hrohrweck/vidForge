import json
import random
from pathlib import Path
from typing import Any

from app.config import get_settings

settings = get_settings()


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
