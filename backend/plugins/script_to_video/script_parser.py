"""Script parser — extracts narration and visual cues from annotated scripts."""

from __future__ import annotations

import re
from typing import Any


def parse_script(script: str) -> list[dict[str, Any]]:
    """Parse a script with ``[bracketed annotations]`` into segments.

    Returns a list of dicts:
    ``{"narration": str, "visual_cue": str | None, "original": str}``
    """
    segments: list[dict[str, Any]] = []
    # Split by visual annotations
    parts = re.split(r"\[([^\]]+)\]", script)

    narration_buffer = ""
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Narration text
            narration_buffer += part.strip()
        else:
            # Visual annotation
            if narration_buffer.strip():
                segments.append({
                    "narration": narration_buffer.strip(),
                    "visual_cue": part.strip(),
                    "original": narration_buffer.strip(),
                })
                narration_buffer = ""
            else:
                segments.append({
                    "narration": "",
                    "visual_cue": part.strip(),
                    "original": "",
                })

    # Trailing narration
    if narration_buffer.strip():
        segments.append({
            "narration": narration_buffer.strip(),
            "visual_cue": None,
            "original": narration_buffer.strip(),
        })

    # Remove empty segments
    segments = [s for s in segments if s["narration"] or s["visual_cue"]]

    # Assign default visual cues for narration-only segments
    for seg in segments:
        if not seg["visual_cue"] and seg["narration"]:
            seg["visual_cue"] = f"Visual: {seg['narration'][:50]}"

    return segments
