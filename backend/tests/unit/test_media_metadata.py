import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.media_metadata import _aspect_ratio, probe_audio, probe_image, probe_video


def test_aspect_ratio_reduces_dimensions():
    assert _aspect_ratio(1920, 1080) == "16:9"
    assert _aspect_ratio(1024, 768) == "4:3"


class FakeImage:
    size = (320, 180)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_probe_image_reads_dimensions(tmp_path: Path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake image")

    pil_package = SimpleNamespace()
    image_module = SimpleNamespace(open=Mock(return_value=FakeImage()))

    with patch.dict(sys.modules, {"PIL": pil_package, "PIL.Image": image_module}):
        assert probe_image(image_path) == {
            "width": 320,
            "height": 180,
            "aspect_ratio": "16:9",
        }


def test_probe_video_parses_ffprobe_json():
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
            }
        ],
        "format": {"duration": "12.5"},
    }
    completed = Mock(returncode=0, stdout=json.dumps(payload), stderr="")

    with patch("app.services.media_metadata.subprocess.run", return_value=completed):
        metadata = probe_video("video.mp4")

    assert metadata == {
        "width": 1920,
        "height": 1080,
        "aspect_ratio": "16:9",
        "duration": 12.5,
        "fps": 30000 / 1001,
    }


def test_probe_audio_parses_duration():
    payload = {"streams": [{"codec_type": "audio"}], "format": {"duration": "8.25"}}
    completed = Mock(returncode=0, stdout=json.dumps(payload), stderr="")

    with patch("app.services.media_metadata.subprocess.run", return_value=completed):
        assert probe_audio("audio.wav") == {"duration": 8.25}


def test_probe_video_failure_returns_none():
    completed = Mock(returncode=1, stdout="", stderr="ffprobe missing")

    with patch("app.services.media_metadata.subprocess.run", return_value=completed):
        assert probe_video("video.mp4") is None
