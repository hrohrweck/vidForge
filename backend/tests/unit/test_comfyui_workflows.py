from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.providers.comfyui import (
    build_ltx_workflow,
    build_wan_i2v_workflow,
    build_wan_video_workflow,
    upload_image_to_comfyui,
    video_generation_resolution,
)
from app.services.providers.comfyui.workflow_builders import (
    _build_ltx_workflow,
    _build_wan_i2v_workflow,
    _build_wan_video_workflow,
    _upload_image_to_comfyui,
    _video_generation_resolution,
)

WORKFLOWS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "services"
    / "providers"
    / "comfyui"
    / "workflows"
)


class TestVideoGenerationResolution:
    def test_known_aspect_ratios(self) -> None:
        assert video_generation_resolution("16:9") == (848, 480)
        assert video_generation_resolution("9:16") == (480, 848)
        assert video_generation_resolution("1:1") == (640, 640)
        assert video_generation_resolution("4:3") == (640, 480)
        assert video_generation_resolution("3:2") == (640, 432)
        assert video_generation_resolution("21:9") == (848, 384)

    def test_unknown_aspect_ratio_returns_default(self) -> None:
        assert video_generation_resolution("unknown") == (848, 480)

    def test_private_alias_is_same_function(self) -> None:
        assert _video_generation_resolution is video_generation_resolution


class TestBuildWanVideoWorkflow:
    def test_returns_dict_with_expected_nodes(self) -> None:
        workflow = build_wan_video_workflow(
            prompt="a cat walking",
            aspect_ratio="16:9",
            frames=81,
            provider_config={},
        )
        assert isinstance(workflow, dict)
        class_types = {node["class_type"] for node in workflow.values()}
        assert "CLIPLoader" in class_types
        assert "CLIPTextEncode" in class_types
        assert "KSampler" in class_types
        assert "VAEDecode" in class_types
        assert "SaveVideo" in class_types

    def test_prompt_is_injected(self) -> None:
        workflow = build_wan_video_workflow(
            prompt="test prompt value",
            aspect_ratio="16:9",
            frames=81,
            provider_config={},
        )
        texts = [
            node["inputs"]["text"]
            for node in workflow.values()
            if node.get("class_type") == "CLIPTextEncode"
        ]
        assert "test prompt value" in texts

    def test_provider_config_overrides(self) -> None:
        config: dict[str, Any] = {
            "wan_clip_name": "custom_clip.safetensors",
            "wan_video_steps": 50,
            "wan_video_cfg": 7.0,
        }
        workflow = build_wan_video_workflow(
            prompt="test",
            aspect_ratio="16:9",
            frames=81,
            provider_config=config,
        )
        clip_node = next(
            n for n in workflow.values() if n["class_type"] == "CLIPLoader"
        )
        assert clip_node["inputs"]["clip_name"] == "custom_clip.safetensors"

        sampler_node = next(
            n for n in workflow.values() if n["class_type"] == "KSampler"
        )
        assert sampler_node["inputs"]["steps"] == 50
        assert sampler_node["inputs"]["cfg"] == 7.0

    def test_frames_injected_into_latent_video(self) -> None:
        workflow = build_wan_video_workflow(
            prompt="test",
            aspect_ratio="16:9",
            frames=49,
            provider_config={},
        )
        latent_node = next(
            n for n in workflow.values()
            if n["class_type"] == "EmptyHunyuanLatentVideo"
        )
        assert latent_node["inputs"]["length"] == 49

    def test_private_alias_is_same_function(self) -> None:
        assert _build_wan_video_workflow is build_wan_video_workflow


class TestBuildWanI2vWorkflow:
    def test_returns_dict_with_i2v_nodes(self) -> None:
        workflow = build_wan_i2v_workflow(
            prompt="a dog running",
            aspect_ratio="16:9",
            frames=81,
            image_name="test_image.png",
            provider_config={},
        )
        assert isinstance(workflow, dict)
        class_types = {node["class_type"] for node in workflow.values()}
        assert "LoadImage" in class_types
        assert "WanImageToVideo" in class_types
        assert "KSampler" in class_types
        assert "SaveVideo" in class_types

    def test_image_name_injected(self) -> None:
        workflow = build_wan_i2v_workflow(
            prompt="test",
            aspect_ratio="16:9",
            frames=81,
            image_name="my_seed.png",
            provider_config={},
        )
        load_node = next(
            n for n in workflow.values() if n["class_type"] == "LoadImage"
        )
        assert load_node["inputs"]["image"] == "my_seed.png"

    def test_private_alias_is_same_function(self) -> None:
        assert _build_wan_i2v_workflow is build_wan_i2v_workflow


class TestWorkflowJsonTemplates:
    EXPECTED_WORKFLOWS = [
        "flux_image.json",
        "ltx_distilled.json",
        "ltx_i2v.json",
        "ltx_t2v.json",
        "preview.json",
        "wan_i2v.json",
        "wan_s2v.json",
        "wan_t2v.json",
    ]

    def test_workflow_directory_is_not_empty(self) -> None:
        assert WORKFLOWS_DIR.is_dir()
        json_files = list(WORKFLOWS_DIR.glob("*.json"))
        assert len(json_files) >= len(self.EXPECTED_WORKFLOWS)

    TEMPLATE_WORKFLOWS = {"flux_image.json"}

    @pytest.mark.parametrize("filename", EXPECTED_WORKFLOWS)
    def test_workflow_json_is_loadable(self, filename: str) -> None:
        path = WORKFLOWS_DIR / filename
        assert path.exists(), f"Missing workflow file: {filename}"
        raw = path.read_text(encoding="utf-8")
        if filename in self.TEMPLATE_WORKFLOWS:
            raw = raw.replace("{seed}", "0").replace("{width}", "1024").replace("{height}", "1024")
        data = json.loads(raw)
        assert isinstance(data, dict)
        assert len(data) > 0

    @pytest.mark.parametrize("filename", EXPECTED_WORKFLOWS)
    def test_workflow_nodes_have_class_type(self, filename: str) -> None:
        path = WORKFLOWS_DIR / filename
        raw = path.read_text(encoding="utf-8")
        if filename in self.TEMPLATE_WORKFLOWS:
            raw = raw.replace("{seed}", "0").replace("{width}", "1024").replace("{height}", "1024")
        data = json.loads(raw)
        for node_id, node in data.items():
            assert "class_type" in node, (
                f"Node {node_id} in {filename} missing class_type"
            )


class TestImportsAfterMove:
    def test_comfyui_init_exports(self) -> None:
        from app.services.providers.comfyui import (
            build_ltx_workflow as init_ltx,
            build_wan_i2v_workflow as init_i2v,
            build_wan_video_workflow as init_wan,
        )

        assert init_wan is build_wan_video_workflow
        assert init_i2v is build_wan_i2v_workflow
        assert init_ltx is build_ltx_workflow

    def test_upload_alias_is_same_function(self) -> None:
        assert _upload_image_to_comfyui is upload_image_to_comfyui
