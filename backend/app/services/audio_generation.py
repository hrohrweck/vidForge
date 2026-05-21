import asyncio
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
    """Generate background music via the remote AudioCraft container.

    The container exposes a simple REST API at ``/generate``.  This
    service is a thin HTTP client — no model loading happens in the
    backend process.
    """

    def __init__(self, base_url: str | None = None):
        from app.config import get_settings
        settings = get_settings()
        self.base_url = (base_url or settings.audiocraft_url).rstrip("/")

    async def generate(
        self,
        prompt: str,
        output_path: str | None = None,
        duration: float = 10.0,
        output_format: str = "mp3",
    ) -> str:
        """Generate music and return the local file path.

        If *output_path* is given the file is copied there; otherwise
        a path under ``storage/music/`` is used.
        """
        from pathlib import Path

        import httpx

        url = f"{self.base_url}/generate"
        payload = {
            "prompt": prompt,
            "duration": duration,
            "output_format": output_format,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        remote_path = data["path"]

        # If audiocraft container shares the storage volume, the file
        # is already accessible.  Otherwise, download it.
        remote = Path(remote_path)
        if remote.exists():
            if output_path:
                import shutil
                out = Path(output_path)
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(remote), str(out))
                return str(out)
            return str(remote)

        # Fallback: download via HTTP
        filename = data["filename"]
        file_url = f"{self.base_url}/files/{filename}"
        if not output_path:
            output_path = str(Path("./storage/music") / filename)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            async with client.stream("GET", file_url) as stream:
                stream.raise_for_status()
                with open(out, "wb") as f:
                    async for chunk in stream.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

        return str(out)

    async def is_available(self) -> bool:
        """Check if the AudioCraft server is reachable."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


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
