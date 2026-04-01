from dataclasses import dataclass, field
from typing import Literal


@dataclass
class VideoModel:
    id: str
    name: str
    provider: Literal["wan", "ltx"]
    workflow: str
    capabilities: list[str] = field(default_factory=list)
    max_duration: int = 30
    max_resolution: tuple[int, int] = (1920, 1080)
    default_steps: int = 30
    description: str = ""
    distilled: bool = False


MODELS: dict[str, VideoModel] = {
    "wan2.2_t2v": VideoModel(
        id="wan2.2_t2v",
        name="WAN 2.2 Text-to-Video",
        provider="wan",
        workflow="wan_t2v.json",
        capabilities=["text-to-video"],
        max_duration=30,
        max_resolution=(1920, 1080),
        default_steps=30,
        description="WAN 2.2 5B model for text-to-video generation. Good quality, moderate speed.",
    ),
    "wan2.2_s2v": VideoModel(
        id="wan2.2_s2v",
        name="WAN 2.2 Scene-to-Video",
        provider="wan",
        workflow="wan_s2v.json",
        capabilities=["text-to-video", "scene-to-video"],
        max_duration=30,
        max_resolution=(1920, 1080),
        default_steps=30,
        description="WAN 2.2 5B model optimized for scene continuation.",
    ),
    "ltx2.3_t2v": VideoModel(
        id="ltx2.3_t2v",
        name="LTX 2.3 Text-to-Video",
        provider="ltx",
        workflow="ltx_t2v.json",
        capabilities=["text-to-video", "audio-to-video"],
        max_duration=20,
        max_resolution=(1920, 1080),
        default_steps=30,
        description="LTX 2.3 full model with native audio-video support. Highest quality.",
    ),
    "ltx2.3_distilled": VideoModel(
        id="ltx2.3_distilled",
        name="LTX 2.3 Distilled (Fast)",
        provider="ltx",
        workflow="ltx_distilled.json",
        capabilities=["text-to-video", "audio-to-video"],
        max_duration=20,
        max_resolution=(1920, 1080),
        default_steps=8,
        distilled=True,
        description="LTX 2.3 distilled model for fast 8-step inference. Good for iteration.",
    ),
    "ltx2.3_i2v": VideoModel(
        id="ltx2.3_i2v",
        name="LTX 2.3 Image-to-Video",
        provider="ltx",
        workflow="ltx_i2v.json",
        capabilities=["image-to-video", "audio-to-video"],
        max_duration=20,
        max_resolution=(1920, 1080),
        default_steps=30,
        description="LTX 2.3 for image animation with audio support.",
    ),
}


def get_model(model_id: str) -> VideoModel | None:
    return MODELS.get(model_id)


def get_all_models() -> list[VideoModel]:
    return list(MODELS.values())


def get_models_by_capability(capability: str) -> list[VideoModel]:
    return [m for m in MODELS.values() if capability in m.capabilities]


def get_models_by_provider(provider: str) -> list[VideoModel]:
    return [m for m in MODELS.values() if m.provider == provider]


def validate_model_for_template(model_id: str, template_type: str) -> bool:
    model = get_model(model_id)
    if not model:
        return False
    capability_map = {
        "text-to-video": "text-to-video",
        "scene-to-video": "scene-to-video",
        "image-to-video": "image-to-video",
        "audio-to-video": "audio-to-video",
    }
    required = capability_map.get(template_type)
    if not required:
        return True
    return required in model.capabilities
