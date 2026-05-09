"""Regression tests: verify dead fields stay removed from music_video_scene template."""
from pathlib import Path

from app.services.template_loader import TemplateLoader

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"


def _load(name: str) -> dict:
    loader = TemplateLoader(str(TEMPLATES_DIR))
    return loader.load_template(name)


DEAD_INPUTS = {"image_provider", "video_provider", "background_music", "background_music_volume"}
EXPECTED_INPUTS = ["audio_file", "style", "aspect_ratio"]
EXPECTED_PIPELINE = [
    "extract_lyrics",
    "plan_scenes",
    "generate_seed_images",
    "generate_scene_videos",
    "merge_scenes",
    "generate_preview",
]


def test_music_video_scene_template_has_no_dead_inputs():
    """Dead provider/background_music inputs must not appear in music_video_scene template."""
    t = _load("music_video_scene")
    input_names = [i["name"] for i in t["inputs"]]
    dead_found = DEAD_INPUTS & set(input_names)
    assert not dead_found, (
        f"Dead inputs still present in music_video_scene.yaml: {sorted(dead_found)}. "
        f"Full input list: {input_names}"
    )
    assert input_names == EXPECTED_INPUTS, (
        f"Expected inputs {EXPECTED_INPUTS}, got {input_names}"
    )


def test_music_video_scene_template_has_no_dead_pipeline_steps():
    """mix_audio step and provider interpolations must not appear in music_video_scene pipeline."""
    t = _load("music_video_scene")
    step_names = [s["step"] for s in t["pipeline"]]
    assert "mix_audio" not in step_names, (
        f"Orphan 'mix_audio' step still in pipeline: {step_names}"
    )
    assert step_names == EXPECTED_PIPELINE, (
        f"Expected pipeline steps {EXPECTED_PIPELINE}, got {step_names}"
    )
    # No step should reference dead provider interpolation variables
    for step in t["pipeline"]:
        provider_val = step.get("provider", "")
        assert "${image_provider}" not in str(provider_val), (
            f"Step '{step['step']}' still references dead ${{image_provider}}"
        )
        assert "${video_provider}" not in str(provider_val), (
            f"Step '{step['step']}' still references dead ${{video_provider}}"
        )


def test_script_to_video_template_unchanged_background_music_field():
    """script_to_video.yaml must STILL have its background_music boolean input — guardrail test."""
    t = _load("script_to_video")
    input_names = [i["name"] for i in t["inputs"]]
    assert "background_music" in input_names, (
        f"'background_music' was accidentally removed from script_to_video.yaml! "
        f"Input list: {input_names}. This field belongs there (it's a boolean toggle for "
        f"AI-generated music — different semantics from the file-upload in music_video_scene)."
    )
    # Also assert it's a boolean type (not a file upload — confirms we didn't corrupt the type)
    bg_input = next(i for i in t["inputs"] if i["name"] == "background_music")
    assert bg_input["type"] == "boolean", (
        f"Expected background_music to be boolean in script_to_video, got: {bg_input['type']}"
    )
