import json
from pathlib import Path
from typing import Any

import yaml


class StyleLoader:
    """Load and validate style presets from YAML files."""

    def __init__(self, styles_dir: str = "styles"):
        base = Path(styles_dir)
        if not base.is_absolute():
            candidate = Path.cwd() / base
            if candidate.exists():
                base = candidate
            else:
                fallback = Path(__file__).resolve().parents[2] / styles_dir
                if fallback.exists():
                    base = fallback
        self.styles_dir = base

    def load_style(self, name: str) -> dict[str, Any]:
        """Load a style by name (without .yaml extension) or by style name field."""
        style_path = self.styles_dir / f"{name}.yaml"
        if style_path.exists():
            with open(style_path) as f:
                return yaml.safe_load(f)

        for style_path in self.styles_dir.glob("*.yaml"):
            with open(style_path) as f:
                style = yaml.safe_load(f)
                if style.get("name") == name:
                    return style

        raise FileNotFoundError(f"Style not found: {name}")

    def load_all_styles(self) -> list[dict[str, Any]]:
        """Load all styles from the styles directory."""
        styles = []
        for style_path in self.styles_dir.glob("*.yaml"):
            with open(style_path) as f:
                style = yaml.safe_load(f)
                style["_source_file"] = style_path.stem
                styles.append(style)
        return styles

    def validate_style(self, style: dict[str, Any]) -> bool:
        """Validate a style has required fields."""
        required_fields = ["name", "params"]
        for field in required_fields:
            if field not in style:
                raise ValueError(f"Style missing required field: {field}")
        return True


def load_comfyui_workflow(workflow_path: str) -> dict[str, Any]:
    """Load a ComfyUI workflow JSON file."""
    with open(workflow_path) as f:
        return json.load(f)


def merge_style_into_workflow(
    workflow: dict[str, Any], style_params: dict[str, Any]
) -> dict[str, Any]:
    """Merge style parameters into a ComfyUI workflow."""
    workflow = workflow.copy()

    for node_id, node in workflow.items():
        if "inputs" in node:
            for key, value in style_params.items():
                if key in node["inputs"]:
                    node["inputs"][key] = value

    return workflow
