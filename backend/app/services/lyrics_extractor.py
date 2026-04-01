import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()


class LyricsExtractorError(Exception):
    pass


class LyricsExtractor:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=300.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def extract_from_audio(self, audio_path: str) -> dict[str, Any]:
        try:
            result = await self._run_whisper(audio_path)
            return result
        except Exception as e:
            raise LyricsExtractorError(f"Failed to extract lyrics: {e}")

    async def _run_whisper(self, audio_path: str) -> dict[str, Any]:
        whisper_url = f"{settings.ollama_url}/api/transcribe"

        try:
            with open(audio_path, "rb") as audio_file:
                files = {"file": audio_file}
                data = {
                    "model": "whisper-base",
                    "language": "en",
                }
                response = await self.client.post(
                    whisper_url,
                    files=files,
                    data=data,
                )

            if response.status_code != 200:
                raise LyricsExtractorError(f"Whisper API error: {response.status_code}")

            result = response.json()
            return self._parse_transcript_with_timestamps(result, audio_path)
        except FileNotFoundError:
            raise LyricsExtractorError(f"Audio file not found: {audio_path}")
        except httpx.HTTPError as e:
            raise LyricsExtractorError(f"HTTP error during transcription: {e}")

    def _parse_transcript_with_timestamps(
        self, transcript: dict, audio_path: str
    ) -> dict[str, Any]:
        text = transcript.get("text", "")

        duration = self._get_audio_duration(audio_path)

        words = transcript.get("words", [])
        if not words:
            words = self._approximate_word_timestamps(text, duration)

        lyrics = []
        for word_info in words:
            lyrics.append(
                {
                    "text": word_info.get("text", ""),
                    "start": word_info.get("start", 0.0),
                    "end": word_info.get("end", 0.0),
                }
            )

        lines = self._group_into_lines(lyrics)

        return {
            "lyrics": lyrics,
            "lines": lines,
            "full_text": text,
            "duration": duration,
        }

    def _approximate_word_timestamps(
        self, text: str, duration: float
    ) -> list[dict[str, Any]]:
        words = text.split()
        if not words:
            return []

        total_words = len(words)
        avg_word_duration = duration / max(total_words, 1)

        word_timestamps = []
        current_time = 0.0

        for word in words:
            word_timestamps.append(
                {
                    "text": word,
                    "start": current_time,
                    "end": current_time + avg_word_duration,
                }
            )
            current_time += avg_word_duration

        return word_timestamps

    def _group_into_lines(
        self, words: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not words:
            return []

        lines = []
        current_line = {"text": "", "start": 0.0, "end": 0.0, "words": []}

        for word in words:
            if not current_line["text"]:
                current_line["start"] = word["start"]

            current_line["text"] += " " + word["text"]
            current_line["words"].append(word)
            current_line["end"] = word["end"]

            if word["text"].endswith((".", "!", "?", ",", "\n")) or len(
                current_line["words"]
            ) >= 10:
                current_line["text"] = current_line["text"].strip()
                lines.append(current_line)
                current_line = {"text": "", "start": 0.0, "end": 0.0, "words": []}

        if current_line["text"]:
            current_line["text"] = current_line["text"].strip()
            lines.append(current_line)

        return lines

    def _get_audio_duration(self, audio_path: str) -> float:
        try:
            import subprocess

            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass
        return 30.0

    @staticmethod
    def parse_manual_lyrics(
        lyrics_text: str, duration: float
    ) -> dict[str, Any]:
        lines = []
        words = []
        current_time = 0.0

        line_duration = duration / max(len(lyrics_text.split("\n")), 1)

        for line in lyrics_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            line_words = line.split()
            words_in_line = len(line_words)
            word_duration = line_duration / max(words_in_line, 1)

            line_start = current_time

            for word in line_words:
                word_start = current_time
                word_end = current_time + word_duration
                words.append(
                    {
                        "text": word,
                        "start": round(word_start, 2),
                        "end": round(word_end, 2),
                    }
                )
                current_time = word_end

            lines.append(
                {
                    "text": line,
                    "start": round(line_start, 2),
                    "end": round(current_time, 2),
                    "words": [
                        w for w in words if w["start"] >= line_start and w["end"] <= current_time
                    ],
                }
            )

        return {
            "lyrics": words,
            "lines": lines,
            "full_text": lyrics_text,
            "duration": duration,
        }
