"""TTS (text-to-speech) for script narration using edge-tts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VOICE_MAP = {
    "default": "en-US-AndrewNeural",
    "male": "en-US-GuyNeural",
    "female": "en-US-JennyNeural",
    "deep": "en-US-DavisNeural",
}


async def generate_narration(
    segments: list[str],
    voice: str = "default",
    output_dir: Path | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Generate narration audio for each segment.

    Returns ``(audio_path, timings)`` where *timings* is a list of
    ``{"start": float, "end": float, "text": str}`` dicts.
    """
    try:
        import edge_tts
    except ImportError:
        raise RuntimeError("edge-tts is required for TTS. Install with: pip install edge-tts")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    voice_name = VOICE_MAP.get(voice, VOICE_MAP["default"])
    timings: list[dict[str, Any]] = []
    audio_paths: list[str] = []

    for i, text in enumerate(segments):
        if not text.strip():
            continue

        out_file = (output_dir or Path(".")) / f"narration_{i:03d}.mp3"

        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(str(out_file))

        # Get word-level timing
        word_timings = []
        try:
            async with edge_tts.Communicate(text, voice_name) as stream:
                async for chunk in stream.stream():
                    if chunk["type"] == "WordBoundary":
                        word_timings.append({
                            "start": chunk["offset_ms"] / 1000.0,
                            "end": (chunk["offset_ms"] + chunk["duration_ms"]) / 1000.0,
                            "text": chunk["text"],
                        })
        except Exception:
            pass

        duration = 0.0
        if word_timings:
            duration = word_timings[-1]["end"]
        else:
            # Fallback: estimate from file size or word count
            duration = len(text.split()) / 2.5

        offset = timings[-1]["end"] if timings else 0.0
        timings.append({
            "start": offset,
            "end": offset + duration,
            "text": text,
            "word_timings": word_timings,
        })
        audio_paths.append(str(out_file))

    # If multiple segments, concatenate
    if len(audio_paths) == 0:
        return "", []
    elif len(audio_paths) == 1:
        return audio_paths[0], timings
    else:
        combined = (output_dir or Path(".")) / "narration_combined.mp3"
        await _concatenate_mp3(audio_paths, str(combined))
        return str(combined), timings


async def _concatenate_mp3(paths: list[str], output: str) -> None:
    """Concatenate multiple MP3 files using ffmpeg."""
    import subprocess

    # Create a concat list file
    list_file = Path(output).with_suffix(".txt")
    with open(list_file, "w") as f:
        for p in paths:
            f.write(f"file '{p}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", output,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    list_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {proc.stderr}")
