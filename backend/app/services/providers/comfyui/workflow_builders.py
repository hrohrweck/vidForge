"""ComfyUI workflow builder utilities.

Extracted from media_generator.py so that all ComfyUI-based providers
(ComfyUIDirectProvider, RunPodProvider, etc.) can share workflow construction.
"""

import json
import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.model_config_service import ModelConfigService

if TYPE_CHECKING:
    from app.services.providers.comfyui_direct import ComfyUIDirectProvider

settings = get_settings()
logger = logging.getLogger(__name__)


def video_generation_resolution(aspect_ratio: str) -> tuple[int, int]:
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


_video_generation_resolution = video_generation_resolution


async def upload_image_to_comfyui(
    instance: "ComfyUIDirectProvider",
    image_path: Path,
) -> str:
    """Upload an image to ComfyUI's input directory and return its name."""
    image_data = image_path.read_bytes()
    filename = image_path.name
    return await instance.client.upload_file(filename, image_data)


_upload_image_to_comfyui = upload_image_to_comfyui


def build_wan_video_workflow(
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

    clip_name = str(
        provider_config.get("wan_clip_name") or "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    )
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
            "inputs": {
                "video": ["10", 0],
                "filename_prefix": "vidforge",
                "format": "mp4",
                "codec": "h264",
            },
        },
    }


_build_wan_video_workflow = build_wan_video_workflow


def build_wan_i2v_workflow(
    prompt: str,
    aspect_ratio: str,
    frames: int,
    image_name: str,
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    """Build a Wan2.2 I2V (image-to-video) workflow.

    Uses the reference image as the first frame latent, producing
    a video that continues from the seed image.
    """
    width, height = _video_generation_resolution(aspect_ratio)
    seed = random.randint(0, 2**31 - 1)

    clip_name = str(
        provider_config.get("wan_clip_name") or "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    )
    vae_name = str(provider_config.get("wan_vae_name") or "wan2.2_vae.safetensors")
    unet_name = str(provider_config.get("wan_unet_name") or "wan2.2_ti2v_5B_fp16.safetensors")

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
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        "8": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "vae": ["4", 0],
                "width": width,
                "height": height,
                "length": frames,
                "batch_size": 1,
                "start_image": ["7", 0],
            },
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["6", 0],
                "positive": ["8", 0],
                "negative": ["8", 1],
                "latent_image": ["8", 2],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["4", 0]},
        },
        "11": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["10", 0], "fps": fps},
        },
        "12": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["11", 0],
                "filename_prefix": "vidforge",
                "format": "mp4",
                "codec": "h264",
            },
        },
    }


_build_wan_i2v_workflow = build_wan_i2v_workflow


async def build_ltx_workflow(
    prompt: str,
    aspect_ratio: str,
    frames: int,
    variant_id: str,
    reference_image_path: str | None,
    instance: "ComfyUIDirectProvider",
    db: AsyncSession,
) -> dict[str, Any]:
    """Load and parameterise an LTX workflow JSON for the requested variant."""
    config = await ModelConfigService.get_by_id(db, variant_id, instance.provider_id)
    if not config or not config.comfyui_workflow:
        raise ValueError(f"No workflow config for variant: {variant_id}")
    workflow_file = config.comfyui_workflow

    workflow_path = Path(__file__).resolve().parent / "workflows" / workflow_file
    if not workflow_path.exists():
        raise ValueError(f"LTX workflow file not found: {workflow_path}")

    with workflow_path.open("r", encoding="utf-8") as f:
        workflow: dict[str, Any] = json.load(f)

    width, height = _video_generation_resolution(aspect_ratio)
    seed = random.randint(0, 2**31 - 1)

    text_encode_nodes: list[str] = []
    latent_node: str | None = None
    sampler_node: str | None = None
    video_node: str | None = None
    image_node: str | None = None

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        if class_type == "CLIPTextEncode":
            text_encode_nodes.append(node_id)
        elif class_type in ("EmptyLTXVLatentVideo", "LTXVImgToVideo"):
            latent_node = node_id
        elif class_type == "KSampler":
            sampler_node = node_id
        elif class_type == "CreateVideo":
            video_node = node_id
        elif class_type == "LoadImage":
            image_node = node_id

    if len(text_encode_nodes) < 2:
        raise ValueError("LTX workflow must contain at least two CLIPTextEncode nodes")
    if not latent_node:
        raise ValueError("LTX workflow missing latent node")
    if not sampler_node:
        raise ValueError("LTX workflow missing KSampler node")
    if not video_node:
        raise ValueError("LTX workflow missing CreateVideo node")

    workflow[text_encode_nodes[0]]["inputs"]["text"] = prompt
    workflow[text_encode_nodes[1]]["inputs"]["text"] = ""

    workflow[latent_node]["inputs"]["width"] = width
    workflow[latent_node]["inputs"]["height"] = height
    workflow[latent_node]["inputs"]["length"] = frames

    workflow[sampler_node]["inputs"]["seed"] = seed
    workflow[sampler_node]["inputs"]["steps"] = 30
    workflow[sampler_node]["inputs"]["cfg"] = 3.0

    workflow[video_node]["inputs"]["fps"] = 16

    if image_node and reference_image_path:
        image_path = Path(settings.storage_path) / reference_image_path
        if image_path.exists():
            image_name = await _upload_image_to_comfyui(instance, image_path)
            workflow[image_node]["inputs"]["image"] = image_name

    return workflow


_build_ltx_workflow = build_ltx_workflow
