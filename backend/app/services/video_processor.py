import asyncio
import subprocess
from pathlib import Path
from typing import Optional


class VideoProcessor:
    """Video processing utilities using FFmpeg."""

    @staticmethod
    async def get_video_info(video_path: str) -> dict:
        """Get video metadata using ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        import json

        return json.loads(stdout.decode())

    @staticmethod
    async def get_duration(video_path: str) -> float:
        """Get video duration in seconds."""
        info = await VideoProcessor.get_video_info(video_path)
        return float(info.get("format", {}).get("duration", 0))

    @staticmethod
    async def generate_preview(
        input_path: str,
        output_path: str,
        width: int = 854,
        height: int = 480,
        fps: int = 15,
        quality: int = 28,
    ) -> str:
        """Generate a low-resolution preview of a video."""
        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-vf",
            f"scale={width}:{height},fps={fps}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            str(quality),
            "-an",
            "-y",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return output_path

    @staticmethod
    async def merge_videos(
        video_paths: list[str],
        output_path: str,
        transition_duration: float = 0.0,
    ) -> str:
        """Merge multiple video files into one."""
        if len(video_paths) == 0:
            raise ValueError("No videos to merge")

        if len(video_paths) == 1:
            Path(video_paths[0]).rename(output_path)
            return output_path

        list_file = Path(output_path).parent / "concat_list.txt"
        with open(list_file, "w") as f:
            for path in video_paths:
                f.write(f"file '{path}'\n")

        cmd = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-y",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        list_file.unlink()
        return output_path

    @staticmethod
    async def add_audio(
        video_path: str,
        audio_path: str,
        output_path: str,
        audio_volume: float = 1.0,
        video_volume: float = 0.0,
    ) -> str:
        """Add or replace audio track in video."""
        filter_parts = []

        if audio_volume != 1.0:
            filter_parts.append(f"[0:a]volume={audio_volume}[a1]")
        if video_volume > 0:
            filter_parts.append(f"[1:a]volume={video_volume}[a2]")

        filter_complex = "; ".join(filter_parts) if filter_parts else None

        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-i",
            audio_path,
        ]

        if filter_complex:
            cmd.extend(["-filter_complex", filter_complex])

        cmd.extend(
            [
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-y",
                output_path,
            ]
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return output_path

    @staticmethod
    async def mix_audio(
        audio_paths: list[str],
        output_path: str,
        volumes: Optional[list[float]] = None,
        duration: Optional[float] = None,
    ) -> str:
        """Mix multiple audio tracks."""
        if volumes is None:
            volumes = [1.0] * len(audio_paths)

        inputs = []
        filter_parts = []

        for i, (path, vol) in enumerate(zip(audio_paths, volumes)):
            inputs.extend(["-i", path])
            if vol != 1.0:
                filter_parts.append(f"[{i}:a]volume={vol}[a{i}]")

        filter_parts.append(
            f"{''.join(f'[a{i}]' if filter_parts else f'[{i}:a]' for i in range(len(audio_paths)))}"
            f"amix=inputs={len(audio_paths)}:duration=longest[out]"
        )

        cmd = inputs + [
            "-filter_complex",
            "; ".join(filter_parts),
            "-map",
            "[out]",
            "-y",
            output_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return output_path

    @staticmethod
    async def extract_audio(video_path: str, audio_path: str) -> str:
        """Extract audio from video file."""
        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-vn",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            "-y",
            audio_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return audio_path
