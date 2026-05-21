"""Music video scene planner — thin async wrapper."""

from __future__ import annotations

from typing import Any

from app.services.music_video_planner import MusicVideoPlanner


async def plan_music_video(
    lyrics: dict[str, Any],
    duration: float,
    style: str = "realistic",
) -> dict[str, Any]:
    """Plan music video scenes from lyrics."""
    planner = MusicVideoPlanner()
    try:
        return await planner.plan_music_video(lyrics=lyrics, duration=duration, style=style)
    finally:
        await planner.close()
