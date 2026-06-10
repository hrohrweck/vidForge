import tempfile
from pathlib import Path

import pytest
import yaml

from app.services.template_loader import StyleLoader


class TestStyleLoaderValidation:
    """Style validation tests."""

    @pytest.fixture
    def temp_styles_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_reject_style_missing_name(self, temp_styles_dir):
        style_data = {
            "description": "Test style",
            "params": {"prompt_suffix": "test"},
        }

        style_file = temp_styles_dir / "invalid.yaml"
        with open(style_file, "w") as f:
            yaml.dump(style_data, f)

        loader = StyleLoader(str(temp_styles_dir))

        with pytest.raises(ValueError, match="missing required field"):
            loader.validate_style(style_data)

    def test_load_valid_style(self, temp_styles_dir):
        style_data = {
            "name": "Valid Style",
            "description": "A valid style",
            "params": {"prompt_suffix": "test"},
        }

        style_file = temp_styles_dir / "valid.yaml"
        with open(style_file, "w") as f:
            yaml.dump(style_data, f)

        loader = StyleLoader(str(temp_styles_dir))
        loaded = loader.load_style("valid")

        assert loaded["name"] == "Valid Style"
        assert loaded["params"]["prompt_suffix"] == "test"

    def test_handle_missing_style_file(self, temp_styles_dir):
        loader = StyleLoader(str(temp_styles_dir))

        with pytest.raises(FileNotFoundError, match="Style not found"):
            loader.load_style("nonexistent")
