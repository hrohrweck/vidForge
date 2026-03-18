import pytest
import tempfile
import yaml
from pathlib import Path
from app.services.template_loader import TemplateLoader, StyleLoader


class TestTemplateLoaderValidation:
    """Template validation tests."""

    @pytest.fixture
    def temp_templates_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_reject_template_missing_name(self, temp_templates_dir):
        template_data = {
            "description": "Test template",
            "inputs": [{"name": "prompt", "type": "text"}],
            "pipeline": [{"step": "generate"}],
        }

        template_file = temp_templates_dir / "invalid.yaml"
        with open(template_file, "w") as f:
            yaml.dump(template_data, f)

        loader = TemplateLoader(str(temp_templates_dir))

        with pytest.raises(ValueError, match="missing required field"):
            loader.validate_template(template_data)

    def test_reject_template_missing_inputs(self, temp_templates_dir):
        template_data = {
            "name": "Test Template",
            "description": "Test template",
            "pipeline": [{"step": "generate"}],
        }

        template_file = temp_templates_dir / "invalid.yaml"
        with open(template_file, "w") as f:
            yaml.dump(template_data, f)

        loader = TemplateLoader(str(temp_templates_dir))

        with pytest.raises(ValueError, match="missing required field"):
            loader.validate_template(template_data)

    def test_reject_template_missing_pipeline(self, temp_templates_dir):
        template_data = {
            "name": "Test Template",
            "description": "Test template",
            "inputs": [{"name": "prompt", "type": "text"}],
        }

        template_file = temp_templates_dir / "invalid.yaml"
        with open(template_file, "w") as f:
            yaml.dump(template_data, f)

        loader = TemplateLoader(str(temp_templates_dir))

        with pytest.raises(ValueError, match="missing required field"):
            loader.validate_template(template_data)

    def test_load_valid_template(self, temp_templates_dir):
        template_data = {
            "name": "Valid Template",
            "description": "A valid template",
            "inputs": [{"name": "prompt", "type": "text", "required": True}],
            "pipeline": [{"step": "generate", "model": "wan_t2v"}],
        }

        template_file = temp_templates_dir / "valid.yaml"
        with open(template_file, "w") as f:
            yaml.dump(template_data, f)

        loader = TemplateLoader(str(temp_templates_dir))
        loaded = loader.load_template("valid")

        assert loaded["name"] == "Valid Template"
        assert len(loaded["inputs"]) == 1
        assert len(loaded["pipeline"]) == 1

    def test_handle_missing_template_file(self, temp_templates_dir):
        loader = TemplateLoader(str(temp_templates_dir))

        with pytest.raises(FileNotFoundError, match="Template not found"):
            loader.load_template("nonexistent")

    def test_handle_malformed_yaml(self, temp_templates_dir):
        template_file = temp_templates_dir / "malformed.yaml"
        with open(template_file, "w") as f:
            f.write("invalid: yaml: content: [")

        loader = TemplateLoader(str(temp_templates_dir))

        with pytest.raises(yaml.YAMLError):
            loader.load_template("malformed")


class TestTemplateLoaderOperations:
    """Functional tests for template loading."""

    @pytest.fixture
    def temp_templates_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            templates_path = Path(tmpdir)

            template1 = {
                "name": "Template 1",
                "description": "First template",
                "inputs": [{"name": "prompt", "type": "text"}],
                "pipeline": [{"step": "generate"}],
            }
            with open(templates_path / "template1.yaml", "w") as f:
                yaml.dump(template1, f)

            template2 = {
                "name": "Template 2",
                "description": "Second template",
                "inputs": [{"name": "audio", "type": "file"}],
                "pipeline": [{"step": "process"}],
            }
            with open(templates_path / "template2.yaml", "w") as f:
                yaml.dump(template2, f)

            yield templates_path

    def test_load_all_templates(self, temp_templates_dir):
        loader = TemplateLoader(str(temp_templates_dir))
        templates = loader.load_all_templates()

        assert len(templates) == 2
        names = [t["name"] for t in templates]
        assert "Template 1" in names
        assert "Template 2" in names

    def test_load_builtin_templates(self):
        loader = TemplateLoader("backend/templates")

        try:
            templates = loader.load_all_templates()
            template_names = [t["name"] for t in templates]

            assert "Music Video" in template_names
            assert "Prompt to Video" in template_names
            assert "Script to Video" in template_names
        except FileNotFoundError:
            pytest.skip("Backend templates directory not found")

    def test_template_paths_are_safe(self, temp_templates_dir):
        loader = TemplateLoader(str(temp_templates_dir))

        with pytest.raises(FileNotFoundError):
            loader.load_template("../../../etc/passwd")


class TestStyleLoaderValidation:
    """Style preset validation tests."""

    @pytest.fixture
    def temp_styles_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_reject_style_missing_name(self, temp_styles_dir):
        style_data = {"category": "artistic", "params": {"style_strength": 0.8}}

        style_file = temp_styles_dir / "invalid.yaml"
        with open(style_file, "w") as f:
            yaml.dump(style_data, f)

        loader = StyleLoader(str(temp_styles_dir))

        with pytest.raises(ValueError, match="missing required field"):
            loader.validate_style(style_data)

    def test_reject_style_missing_params(self, temp_styles_dir):
        style_data = {"name": "Test Style", "category": "artistic"}

        style_file = temp_styles_dir / "invalid.yaml"
        with open(style_file, "w") as f:
            yaml.dump(style_data, f)

        loader = StyleLoader(str(temp_styles_dir))

        with pytest.raises(ValueError, match="missing required field"):
            loader.validate_style(style_data)

    def test_load_valid_style(self, temp_styles_dir):
        style_data = {
            "name": "Anime Style",
            "category": "artistic",
            "params": {"style_prompt": "anime style", "style_strength": 0.9},
        }

        style_file = temp_styles_dir / "anime.yaml"
        with open(style_file, "w") as f:
            yaml.dump(style_data, f)

        loader = StyleLoader(str(temp_styles_dir))
        loaded = loader.load_style("anime")

        assert loaded["name"] == "Anime Style"
        assert loaded["category"] == "artistic"
        assert "style_prompt" in loaded["params"]

    def test_load_all_styles(self, temp_styles_dir):
        style1 = {"name": "Style 1", "params": {"param1": "value1"}}
        style2 = {"name": "Style 2", "params": {"param2": "value2"}}

        with open(temp_styles_dir / "style1.yaml", "w") as f:
            yaml.dump(style1, f)
        with open(temp_styles_dir / "style2.yaml", "w") as f:
            yaml.dump(style2, f)

        loader = StyleLoader(str(temp_styles_dir))
        styles = loader.load_all_styles()

        assert len(styles) == 2
        names = [s["name"] for s in styles]
        assert "Style 1" in names
        assert "Style 2" in names
