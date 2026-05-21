"""Audio utility functions for the music video plugin."""

from __future__ import annotations

import subprocess


async def get_audio_duration(path: str) -> float:
    """Return the duration of an audio file in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())
