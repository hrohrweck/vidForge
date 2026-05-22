"""Media metadata extraction helpers."""

import json
import logging
import subprocess
from fractions import Fraction
from importlib import import_module
from math import gcd
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _aspect_ratio(width: int, height: int) -> str | None:
    """Return a reduced aspect ratio string like ``16:9``."""
    if width <= 0 or height <= 0:
        return None

    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def probe_image(file_path: str | Path) -> dict[str, Any] | None:
    """Probe image dimensions using Pillow."""
    try:
        image_module = import_module("PIL.Image")

        path = Path(file_path)
        with image_module.open(path) as image:
            width, height = image.size

        return {
            "width": width,
            "height": height,
            "aspect_ratio": _aspect_ratio(width, height),
        }
    except Exception as exc:
        logger.warning("Failed to probe image metadata for %s: %s", file_path, exc)
        return None


def probe_video(file_path: str | Path) -> dict[str, Any] | None:
    """Probe video dimensions, duration, and frame rate using ffprobe."""
    try:
        data = _ffprobe(file_path)
        video_stream = next(
            (stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"),
            None,
        )
        if not video_stream:
            logger.warning("Failed to probe video metadata for %s: no video stream", file_path)
            return None

        width = _to_int(video_stream.get("width"))
        height = _to_int(video_stream.get("height"))
        if width is None or height is None:
            logger.warning("Failed to probe video metadata for %s: missing dimensions", file_path)
            return None

        duration = _duration(data, video_stream)
        fps = _frame_rate(video_stream)

        metadata: dict[str, Any] = {
            "width": width,
            "height": height,
            "aspect_ratio": _aspect_ratio(width, height),
        }
        if duration is not None:
            metadata["duration"] = duration
        if fps is not None:
            metadata["fps"] = fps

        return metadata
    except Exception as exc:
        logger.warning("Failed to probe video metadata for %s: %s", file_path, exc)
        return None


def probe_audio(file_path: str | Path) -> dict[str, Any] | None:
    """Probe audio duration using ffprobe."""
    try:
        data = _ffprobe(file_path)
        duration = _duration(data)
        if duration is None:
            logger.warning("Failed to probe audio metadata for %s: missing duration", file_path)
            return None

        return {"duration": duration}
    except Exception as exc:
        logger.warning("Failed to probe audio metadata for %s: %s", file_path, exc)
        return None


def _ffprobe(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")

    return json.loads(result.stdout)


def _duration(data: dict[str, Any], stream: dict[str, Any] | None = None) -> float | None:
    raw_duration = data.get("format", {}).get("duration")
    if raw_duration in (None, "N/A") and stream is not None:
        raw_duration = stream.get("duration")
    return _to_float(raw_duration)


def _frame_rate(stream: dict[str, Any]) -> float | None:
    raw_rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    if not raw_rate or raw_rate == "0/0":
        return None

    try:
        return float(Fraction(str(raw_rate)))
    except (ValueError, ZeroDivisionError):
        return _to_float(raw_rate)


def _to_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
