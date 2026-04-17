import random
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import Provider, Job
from app.services.providers import PoeProvider, ComfyUIDirectProvider, RunPodProvider
from app.services.job_router import JobRouter


settings = get_settings()


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
            if prov.provider_type == "poe":
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


def get_scene_output_dir(job_id: str, scene_number: int) -> Path:
    return Path(settings.storage_path) / "output" / job_id / f"scene_{scene_number:03d}"


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

    if provider_id:
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()
    else:
        result = await db.execute(select(Provider).where(Provider.provider_type == "poe", Provider.is_active == True))  # noqa: E712
        provider = result.scalar_one_or_none()

    if not provider:
        raise ValueError("No image provider available. Please configure a Poe provider.")

    instance = await get_provider_instance(db, provider)

    if not isinstance(instance, PoeProvider):
        raise ValueError(f"Image generation is only supported on Poe providers, got {provider.provider_type}")

    model = model_preference or instance.config.get("default_image_model", "GPT-Image-1")

    content, output_data = await instance.generate_image(
        prompt=prompt,
        model=model,
        aspect_ratio=aspect_ratio,
    )

    if output_data:
        image_path.write_bytes(output_data)
    else:
        raise ValueError("Image generation returned no data")

    relative_path = str(image_path.relative_to(settings.storage_path))

    return relative_path, content, provider.id


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

    if provider_id:
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()
    else:
        result = await db.execute(select(Provider).where(Provider.provider_type == "comfyui_direct", Provider.is_active == True))  # noqa: E712
        provider = result.scalar_one_or_none()

    if not provider:
        router = JobRouter(db)
        candidates = []
        async for prov in router.iterate_providers():
            if prov.provider_type in ("comfyui_direct", "runpod", "poe"):
                candidates.append(prov)

        for candidate in candidates:
            try:
                instance = await get_provider_instance(db, candidate)
                if candidate.provider_type == "comfyui_direct":
                    provider = candidate
                    break
                elif candidate.provider_type == "poe":
                    provider = candidate
                    break
            except Exception:
                continue

    if not provider:
        raise ValueError("No video provider available. Please configure a provider.")

    instance = await get_provider_instance(db, provider)

    if isinstance(instance, PoeProvider):
        model = model_preference or instance.config.get("default_video_model", "Veo-3.1")
        content, output_data = await instance.generate_video(
            prompt=prompt,
            model=model,
            duration=duration,
            aspect_ratio=aspect_ratio,
        )
        if output_data:
            video_path.write_bytes(output_data)
        else:
            raise ValueError("Video generation returned no data")
        return (
            str(video_path.relative_to(settings.storage_path)),
            content,
            provider.id,
            float(duration),
        )

    from app.services import ComfyUIClient

    workflow_map: dict[str, str] = {
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

    workflow_name = workflow_map.get(model_preference or "", "wan_t2v.json")

    workflow_path = Path(settings.storage_path).parent / "workflows" / workflow_name
    if not workflow_path.exists():
        workflow_path = Path(__file__).parent.parent.parent / "templates" / "workflows" / workflow_name

    if workflow_path.exists():
        import json

        workflow = json.loads(workflow_path.read_text())
    else:
        workflow = _build_minimal_workflow(model_preference or "wan2.2_t2v")

    seed = random.randint(0, 2**31 - 1)

    width, height = _aspect_ratio_to_dimensions(aspect_ratio)
    frames = _duration_to_frames(duration)

    for node_id, node in workflow.items():
        if isinstance(node, dict) and "inputs" in node:
            if node["inputs"].get("text") == "${positive_prompt}":
                node["inputs"]["text"] = prompt
            elif "prompt" in node["inputs"]:
                node["inputs"]["prompt"] = prompt
            if "width" in node["inputs"]:
                node["inputs"]["width"] = width
            if "height" in node["inputs"]:
                node["inputs"]["height"] = height
            if "frames" in node["inputs"]:
                node["inputs"]["frames"] = frames
            if "batch_size" in node["inputs"]:
                node["inputs"]["batch_size"] = 1
            if "seed" in node["inputs"]:
                node["inputs"]["seed"] = seed

    if isinstance(instance, ComfyUIDirectProvider):
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

    raise ValueError(f"Unsupported provider type for video generation: {provider.provider_type}")


def _build_minimal_workflow(model: str) -> dict[str, Any]:
    return {
        "1": {
            "inputs": {
                "text": "",
                "clip": ["2", 0],
            },
            "class_type": "CLIPTextEncode",
        },
        "2": {
            "inputs": {"clip": []},
            "class_type": "CLIP",
        },
        "3": {
            "inputs": {
                "width": 1280,
                "height": 720,
                "length": 25,
                "batch_size": 1,
            },
            "class_type": "EmptyHunyuanLatentVideo",
        },
        "4": {
            "inputs": {
                "model": [],
                "positive": ["1", 0],
                "negative": ["1", 0],
                "latent": ["3", 0],
            },
            "class_type": "HunyuanVideoSampler",
        },
    }


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


def _duration_to_frames(duration: int, fps: int = 24) -> int:
    frames = duration * fps
    return max(frames - (frames % 8) + 1, 9)
