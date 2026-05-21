import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import whisper

WHISPER_MODEL_NAME = "base"


class LyricsExtractorError(Exception):
    pass


class LyricsExtractor:
    """Extract lyrics from audio files using OpenAI Whisper (local)."""

    def __init__(self) -> None:
        self._model: whisper.Whisper | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")

    def _load_model(self) -> whisper.Whisper:
        if self._model is None:
            try:
                self._model = whisper.load_model(WHISPER_MODEL_NAME)
            except Exception as e:
                raise LyricsExtractorError(f"Failed to load Whisper model '{WHISPER_MODEL_NAME}': {e}")
        return self._model

    async def close(self) -> None:
        self._executor.shutdown(wait=False)

    async def extract_from_audio(self, audio_path: str) -> dict[str, Any]:
        try:
            result = await self._run_whisper(audio_path)
            return result
        except Exception as e:
            raise LyricsExtractorError(f"Failed to extract lyrics: {e}")

    async def _run_whisper(self, audio_path: str) -> dict[str, Any]:
        model = self._load_model()
        duration = self._get_audio_duration(audio_path)

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                lambda: model.transcribe(audio_path, word_timestamps=True),
            )
        except Exception as e:
            raise LyricsExtractorError(f"Whisper transcription failed: {e}")

        return self._parse_transcript_with_timestamps(result, duration)

    def _parse_transcript_with_timestamps(
        self, transcript: dict[str, Any], duration: float
    ) -> dict[str, Any]:
        text = transcript.get("text", "").strip()

        words: list[dict[str, Any]] = []
        segments = transcript.get("segments", [])

        for segment in segments:
            segment_words = segment.get("words", [])
            if segment_words:
                for word_info in segment_words:
                    words.append(
                        {
                            "text": word_info.get("word", "").strip(),
                            "start": word_info.get("start", 0.0),
                            "end": word_info.get("end", 0.0),
                        }
                    )
            else:
                words.append(
                    {
                        "text": segment.get("text", "").strip(),
                        "start": segment.get("start", 0.0),
                        "end": segment.get("end", 0.0),
                    }
                )

        if not words and text:
            words = self._approximate_word_timestamps(text, duration)

        lines = self._group_into_lines(words)

        return {
            "lyrics": words,
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
