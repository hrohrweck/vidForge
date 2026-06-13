from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.database import Job
from app.services import comfyui_workflows, media_generator
from app.services.providers.base import (
    ImageProvider,
    ProviderCapabilities,
    ProviderConnectionError,
    ProviderInfo,
)


class RetryImageProvider(ImageProvider):
    def __init__(self, failures_before_success: int) -> None:
        self.provider_id = uuid4()
        self.failures_before_success = failures_before_success
        self.calls = 0

    async def initialize(self, config: dict[str, Any]) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(name="retry", provider_type="test", is_available=True)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_image=True)

    async def generate_image(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise ProviderConnectionError("connection refused")
        return "asset", b"image-bytes"


class FatalImageProvider(RetryImageProvider):
    async def generate_image(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str, bytes]:
        self.calls += 1
        raise RuntimeError("invalid prompt")


def test_comfyui_image_workflow_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui_workflows.random, "randint", lambda _start, _end: 12345)

    workflow = media_generator._build_comfyui_image_workflow(
        prompt="golden prompt",
        aspect_ratio="16:9",
        model_preference="wan2.2-it2v",
        provider_config={
            "wan_clip_name": "clip.safetensors",
            "wan_vae_name": "vae.safetensors",
            "image_steps": 12,
            "image_cfg": 4.5,
            "image_sampler": "uni_pc",
            "image_scheduler": "simple",
            "wan_image_shift": 7.0,
        },
    )

    assert workflow == {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "wan"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "golden prompt", "clip": ["1", 0]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 0]}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        "5": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_it2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["5", 0], "shift": 7.0}},
        "7": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": 1280, "height": 720, "length": 1, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["6", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["7", 0], "seed": 12345, "steps": 12, "cfg": 4.5, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "vidforge_seed_image"}},
    }


def test_flux_image_workflow_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui_workflows.random, "randint", lambda _start, _end: 98765)

    workflow = media_generator._build_flux_image_workflow(
        prompt="flux prompt",
        aspect_ratio="1:1",
        provider_config={
            "flux_unet_name": "flux.safetensors",
            "flux_clip_name1": "clip_l.safetensors",
            "flux_clip_name2": "t5xxl.safetensors",
            "flux_vae_name": "ae.safetensors",
        },
    )

    assert workflow == {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "flux prompt", "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {"seed": 98765, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "vidforge_flux_image"}},
    }


@pytest.mark.asyncio
async def test_generate_image_retries_recoverable_errors(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Any,
    tmp_path: Path,
) -> None:
    provider = RetryImageProvider(failures_before_success=2)
    job = Job(id=uuid4(), user_id=uuid4(), title="Retry job", input_data={})
    sleep_calls: list[float] = []

    async def resolve_provider(*_args: Any, **_kwargs: Any) -> tuple[str, Any, RetryImageProvider]:
        return "test-image", provider.provider_id, provider

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(media_generator, "_resolve_image_provider", resolve_provider)
    monkeypatch.setattr(media_generator.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(media_generator.settings, "storage_path", str(tmp_path))

    relative_path, model_label, resolved_provider_id, _cost = await media_generator.generate_image(
        db_session,
        job,
        "retry prompt",
        1,
    )

    assert provider.calls == 3
    assert sleep_calls == [10.0, 20.0]
    assert model_label == "generated_with_test-image"
    assert resolved_provider_id == provider.provider_id
    assert (tmp_path / relative_path).read_bytes() == b"image-bytes"


@pytest.mark.asyncio
async def test_generate_image_does_not_retry_nonrecoverable_errors(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Any,
    tmp_path: Path,
) -> None:
    provider = FatalImageProvider(failures_before_success=0)
    job = Job(id=uuid4(), user_id=uuid4(), title="Fatal job", input_data={})

    async def resolve_provider(*_args: Any, **_kwargs: Any) -> tuple[str, Any, FatalImageProvider]:
        return "test-image", provider.provider_id, provider

    monkeypatch.setattr(media_generator, "_resolve_image_provider", resolve_provider)
    monkeypatch.setattr(media_generator.settings, "storage_path", str(tmp_path))

    with pytest.raises(RuntimeError, match="invalid prompt"):
        await media_generator.generate_image(db_session, job, "fatal prompt", 1)

    assert provider.calls == 1
