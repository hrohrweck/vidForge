"""Clean up dead fields in Music Video (Scene-Based) template"""

from typing import Sequence, Union

from sqlalchemy import text

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import json
    from pathlib import Path

    import yaml

    yaml_path = Path(__file__).resolve().parents[2] / "templates" / "music_video_scene.yaml"
    template_data = yaml.safe_load(yaml_path.read_text())

    new_config = {
        "template_file": "music_video_scene",
        "inputs": template_data.get("inputs", []),
        "pipeline": template_data.get("pipeline", []),
    }

    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE templates SET config = :config "
            "WHERE name = :name AND is_builtin = true"
        ),
        {"config": json.dumps(new_config), "name": "Music Video (Scene-Based)"},
    )


def downgrade() -> None:
    import json

    original_config = {
        "template_file": "music_video_scene",
        "inputs": [
            {
                "name": "audio_file",
                "type": "file",
                "accept": [".mp3", ".wav", ".ogg", ".flac"],
                "required": True,
                "description": "Audio file to create video for",
            },
            {
                "name": "style",
                "type": "select",
                "options": ["realistic", "anime", "manga", "cinematic", "abstract"],
                "default": "realistic",
                "required": True,
                "description": "Visual style for the generated video",
            },
            {
                "name": "aspect_ratio",
                "type": "select",
                "options": ["16:9", "9:16", "1:1"],
                "default": "16:9",
                "required": False,
                "description": "Output video aspect ratio",
            },
            {
                "name": "image_provider",
                "type": "select",
                "options": ["auto", "poe"],
                "default": "auto",
                "required": False,
                "description": "Provider for seed image generation",
            },
            {
                "name": "video_provider",
                "type": "select",
                "options": ["auto", "poe", "comfyui", "runpod"],
                "default": "auto",
                "required": False,
                "description": "Provider for video generation",
            },
            {
                "name": "background_music",
                "type": "file",
                "accept": [".mp3", ".wav", ".ogg", ".flac"],
                "required": False,
                "description": "Background music track (optional)",
            },
            {
                "name": "background_music_volume",
                "type": "number",
                "default": 0.3,
                "min": 0,
                "max": 1,
                "required": False,
                "description": "Background music volume (0-1)",
            },
        ],
        "pipeline": [
            {
                "step": "extract_lyrics",
                "description": "Extract lyrics from audio using Whisper",
                "tool": "whisper",
                "inputs": ["audio_file"],
                "outputs": ["lyrics"],
            },
            {
                "step": "plan_scenes",
                "description": "Plan scenes using LLM based on lyrics and style",
                "model": "llm",
                "inputs": ["lyrics", "style", "aspect_ratio"],
                "outputs": ["scene_plan"],
            },
            {
                "step": "generate_seed_images",
                "description": "Generate seed images for each scene",
                "provider": "${image_provider}",
                "inputs": ["scene_plan"],
                "outputs": ["seed_images"],
            },
            {
                "step": "generate_scene_videos",
                "description": "Generate video for each scene",
                "provider": "${video_provider}",
                "inputs": ["seed_images", "scene_plan"],
                "outputs": ["scene_videos"],
            },
            {
                "step": "merge_scenes",
                "description": "Merge all scene videos into final video",
                "tool": "ffmpeg",
                "inputs": ["scene_videos"],
                "outputs": ["merged_video"],
            },
            {
                "step": "mix_audio",
                "description": "Mix original audio with background music",
                "tool": "ffmpeg",
                "inputs": ["merged_video", "audio_file", "background_music"],
                "params": {"bg_volume": "${background_music_volume}"},
                "outputs": ["final_video"],
            },
            {
                "step": "generate_preview",
                "description": "Generate low-res preview",
                "params": {"width": 854, "height": 480, "fps": 15},
                "outputs": ["preview"],
            },
        ],
    }

    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE templates SET config = :config "
            "WHERE name = :name AND is_builtin = true"
        ),
        {"config": json.dumps(original_config), "name": "Music Video (Scene-Based)"},
    )
