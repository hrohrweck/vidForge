import json
from pathlib import Path
from typing import Any

import yaml


class TemplateLoader:
    """Load and validate video templates from YAML files."""

    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)

    def load_template(self, name: str) -> dict[str, Any]:
        """Load a template by name (without .yaml extension)."""
        template_path = self.templates_dir / f"{name}.yaml"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {name}")

        with open(template_path) as f:
            return yaml.safe_load(f)

    def load_all_templates(self) -> list[dict[str, Any]]:
        """Load all templates from the templates directory."""
        templates = []
        for template_path in self.templates_dir.glob("*.yaml"):
            with open(template_path) as f:
                template = yaml.safe_load(f)
                template["_source_file"] = template_path.stem
                templates.append(template)
        return templates

    def validate_template(self, template: dict[str, Any]) -> bool:
        """Validate a template has required fields."""
        required_fields = ["name", "inputs", "pipeline"]
        for field in required_fields:
            if field not in template:
                raise ValueError(f"Template missing required field: {field}")
        return True


class StyleLoader:
    """Load and validate style presets from YAML files."""

    def __init__(self, styles_dir: str = "styles"):
        self.styles_dir = Path(styles_dir)

    def load_style(self, name: str) -> dict[str, Any]:
        """Load a style by name (without .yaml extension)."""
        style_path = self.styles_dir / f"{name}.yaml"
        if not style_path.exists():
            raise FileNotFoundError(f"Style not found: {name}")

        with open(style_path) as f:
            return yaml.safe_load(f)

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
