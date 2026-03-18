import asyncio
import subprocess
from pathlib import Path
from typing import Any


class TTSError(Exception):
    pass


class TTSService:
    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or Path("./storage/tts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(
        self,
        text: str,
        output_path: str | None = None,
        voice: str = "en-US-AriaNeural",
        speed: float = 1.0,
        backend: str = "edge",
    ) -> str:
        if backend == "edge":
            return await self._edge_tts(text, output_path, voice, speed)
        elif backend == "piper":
            return await self._piper_tts(text, output_path, voice)
        elif backend == "coqui":
            return await self._coqui_tts(text, output_path, voice)
        else:
            raise TTSError(f"Unknown TTS backend: {backend}")

    async def _edge_tts(
        self,
        text: str,
        output_path: str | None,
        voice: str,
        speed: float,
    ) -> str:
        if not output_path:
            import uuid

            output_path = str(self.output_dir / f"{uuid.uuid4()}.mp3")

        cmd = [
            "edge-tts",
            "--text",
            text,
            "--voice",
            voice,
            "--write-media",
            output_path,
        ]

        if speed != 1.0:
            cmd.extend(["--rate", f"{'+' if speed > 1 else ''}{int((speed - 1) * 100)}%"])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise TTSError(f"Edge TTS failed: {stderr.decode()}")

        return output_path

    async def _piper_tts(
        self,
        text: str,
        output_path: str | None,
        voice: str,
    ) -> str:
        if not output_path:
            import uuid

            output_path = str(self.output_dir / f"{uuid.uuid4()}.wav")

        model = voice if voice.endswith(".onnx") else f"{voice}.onnx"

        cmd = [
            "piper",
            "--model",
            model,
            "--output_file",
            output_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(input=text.encode())

        if proc.returncode != 0:
            raise TTSError(f"Piper TTS failed: {stderr.decode()}")

        return output_path

    async def _coqui_tts(
        self,
        text: str,
        output_path: str | None,
        voice: str,
    ) -> str:
        if not output_path:
            import uuid

            output_path = str(self.output_dir / f"{uuid.uuid4()}.wav")

        cmd = [
            "tts",
            "--text",
            text,
            "--model_name",
            voice or "tts_models/en/ljspeech/vits",
            "--out_path",
            output_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise TTSError(f"Coqui TTS failed: {stderr.decode()}")

        return output_path

    async def segment_and_generate(
        self,
        text: str,
        output_dir: Path,
        voice: str = "en-US-AriaNeural",
        max_segment_length: int = 500,
        backend: str = "edge",
    ) -> list[dict[str, Any]]:
        segments = self._split_text(text, max_segment_length)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for i, segment in enumerate(segments):
            output_path = str(output_dir / f"segment_{i:03d}.mp3")
            try:
                audio_path = await self.generate(
                    text=segment,
                    output_path=output_path,
                    voice=voice,
                    backend=backend,
                )
                duration = await self._get_audio_duration(audio_path)
                results.append(
                    {
                        "index": i,
                        "text": segment,
                        "audio_path": audio_path,
                        "duration": duration,
                    }
                )
            except TTSError as e:
                results.append(
                    {
                        "index": i,
                        "text": segment,
                        "error": str(e),
                    }
                )

        return results

    def _split_text(self, text: str, max_length: int) -> list[str]:
        import re

        sentences = re.split(r"(?<=[.!?])\s+", text)
        segments = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= max_length:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    segments.append(current)
                if len(sentence) > max_length:
                    words = sentence.split()
                    chunk = ""
                    for word in words:
                        if len(chunk) + len(word) + 1 <= max_length:
                            chunk = f"{chunk} {word}".strip()
                        else:
                            if chunk:
                                segments.append(chunk)
                            chunk = word
                    if chunk:
                        segments.append(chunk)
                else:
                    current = sentence

        if current:
            segments.append(current)

        return segments

    async def _get_audio_duration(self, audio_path: str) -> float:
        import json

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            audio_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        info = json.loads(stdout.decode())
        return float(info.get("format", {}).get("duration", 0))

    @staticmethod
    async def list_edge_voices() -> list[dict[str, str]]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "edge-tts",
                "--list-voices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            import json

            voices = json.loads(stdout.decode())
            return [
                {
                    "name": v.get("Name", ""),
                    "gender": v.get("Gender", ""),
                    "language": v.get("Locale", ""),
                }
                for v in voices
            ]
        except Exception:
            return []


class MusicGenService:
    def __init__(self, output_dir: Path | None = None, device: str = "cuda"):
        self.output_dir = output_dir or Path("./storage/music")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = device

    async def generate(
        self,
        prompt: str,
        output_path: str | None = None,
        duration: float = 10.0,
        model: str = "facebook/musicgen-small",
    ) -> str:
        if not output_path:
            import uuid

            output_path = str(self.output_dir / f"{uuid.uuid4()}.wav")

        try:
            return await self._generate_with_audiocraft(prompt, output_path, duration, model)
        except ImportError:
            return await self._generate_with_cli(prompt, output_path, duration, model)

    async def _generate_with_audiocraft(
        self,
        prompt: str,
        output_path: str,
        duration: float,
        model: str,
    ) -> str:
        import torch
        from audiocraft.models import MusicGen
        from audiocraft.data.audio import audio_write

        mg = MusicGen.get_pretrained(model, device=self.device)
        mg.set_generation_params(duration=duration)

        wav = mg.generate([prompt])
        wav = wav.cpu()

        for idx, one_wav in enumerate(wav):
            audio_write(
                output_path.replace(".wav", ""),
                one_wav,
                mg.sample_rate,
                strategy="loudness",
            )

        return output_path

    async def _generate_with_cli(
        self,
        prompt: str,
        output_path: str,
        duration: float,
        model: str,
    ) -> str:
        cmd = [
            "python",
            "-m",
            "audiocraft",
            "generate",
            "--prompt",
            prompt,
            "--duration",
            str(duration),
            "--output",
            output_path,
            "--model",
            model,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise TTSError(f"MusicGen failed: {stderr.decode()}")

        return output_path


async def generate_narration(
    text: str,
    output_dir: Path,
    voice: str = "en-US-AriaNeural",
    backend: str = "edge",
) -> tuple[str, float]:
    tts = TTSService(output_dir)
    output_path = str(output_dir / "narration.mp3")

    await tts.generate(text, output_path, voice, backend=backend)
    duration = await tts._get_audio_duration(output_path)

    return output_path, duration


async def generate_background_music(
    prompt: str,
    output_path: str,
    duration: float = 30.0,
) -> str:
    service = MusicGenService()
    return await service.generate(prompt, output_path, duration)
