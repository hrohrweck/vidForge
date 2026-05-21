"""Lyrics extraction from audio files via Whisper."""

from __future__ import annotations

from typing import Any

from app.services.lyrics_extractor import LyricsExtractor


async def extract_lyrics(audio_path: str) -> dict[str, Any]:
    """Extract lyrics from an audio file.

    Returns a dict with keys: ``lyrics``, ``lines``, ``full_text``, ``duration``.
    """
    extractor = LyricsExtractor()
    try:
        return await extractor.extract_from_audio(audio_path)
    finally:
        await extractor.close()
