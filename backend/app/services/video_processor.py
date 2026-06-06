import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ValidationResult:
    valid: bool
    actual_frames: int
    actual_duration: float
    expected_frames: int
    error_message: str | None = None


class InvalidVideoOutputError(Exception):
    def __init__(self, video_path: str, result: ValidationResult):
        self.video_path = video_path
        self.result = result
        msg = (
            result.error_message
            or f"Video at {video_path} is invalid "
            f"(frames={result.actual_frames}, duration={result.actual_duration:.2f}s)"
        )
        super().__init__(msg)


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
    async def pad_to_aspect_ratio(
        input_path: str,
        output_path: str,
        target_aspect: str,
    ) -> str:
        """Pad video with black bars to match target aspect ratio."""
        try:
            w_str, h_str = target_aspect.split(':')
            target_ratio = float(w_str) / float(h_str)
        except ValueError:
            raise ValueError(f"Invalid target aspect ratio: {target_aspect}")

        info = await VideoProcessor.get_video_info(input_path)
        streams = info.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not video_stream:
            raise ValueError(f"No video stream found in {input_path}")

        actual_w = float(video_stream.get("width", 0))
        actual_h = float(video_stream.get("height", 0))
        if actual_w == 0 or actual_h == 0:
            raise ValueError(f"Invalid video dimensions in {input_path}")

        actual_ratio = actual_w / actual_h

        if abs(actual_ratio - target_ratio) <= 0.02:
            shutil.copy(input_path, output_path)
            return output_path

        if actual_ratio > target_ratio:
            new_w = int(actual_w)
            new_h = int(actual_w / target_ratio)
        else:
            new_h = int(actual_h)
            new_w = int(actual_h * target_ratio)

        new_w = new_w if new_w % 2 == 0 else new_w + 1
        new_h = new_h if new_h % 2 == 0 else new_h + 1

        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-vf", f"scale={int(actual_w)}:{int(actual_h)},pad={new_w}:{new_h}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",
            "-y", str(Path(output_path).resolve()),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg pad_to_aspect_ratio failed: {stderr.decode() if stderr else 'Unknown error'}")
        return output_path

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
            str(Path(output_path).resolve()),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg preview failed: {stderr.decode() if stderr else 'Unknown error'}")
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
            shutil.copy(video_paths[0], output_path)
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
            str(Path(output_path).resolve()),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg merge failed: {stderr.decode() if stderr else 'Unknown error'}")
        list_file.unlink()
        return output_path

    @staticmethod
    async def extract_frame(
        video_path: str,
        output_path: str,
        ratio: float = 0.8,
    ) -> str:
        """Extract a single frame from *video_path* at *ratio* (0–1).

        ``ratio=0.8`` grabs a frame at 80 % through the clip, avoiding
        the often-degraded very last frame.
        """
        duration = await VideoProcessor.get_duration(video_path)
        timestamp = duration * ratio

        cmd = [
            "ffmpeg",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-y", str(Path(output_path).resolve()),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg extract_frame failed: {stderr.decode()}")
        return output_path

    @staticmethod
    async def merge_with_crossfade(
        video_paths: list[str],
        output_path: str,
        crossfade_duration: float = 0.3,
    ) -> str:
        """Merge video clips with crossfade transitions.

        Uses FFmpeg's ``xfade`` filter between consecutive clips.
        """
        if len(video_paths) == 0:
            raise ValueError("No videos to merge")
        if len(video_paths) == 1:
            shutil.copy(video_paths[0], output_path)
            return output_path

        durations = []
        for p in video_paths:
            durations.append(await VideoProcessor.get_duration(p))

        # Build xfade filter chain
        # xfade offsets: current_total_duration - crossfade_duration
        filter_parts: list[str] = []
        current_total = durations[0]
        prev_tag = "0:v"
        for i in range(1, len(video_paths)):
            offset = current_total - crossfade_duration
            out_tag = f"v{i:02d}" if i < len(video_paths) - 1 else "vout"
            filter_parts.append(
                f"[{prev_tag}][{i}:v]xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}[{out_tag}]"
            )
            current_total = current_total + durations[i] - crossfade_duration
            prev_tag = out_tag

        inputs: list[str] = []
        for p in video_paths:
            inputs.extend(["-i", p])

        last_out = prev_tag
        filter_complex = "; ".join(filter_parts)

        cmd = [
            "ffmpeg",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{last_out}]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-an",
            "-y", str(Path(output_path).resolve()),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg crossfade merge failed: {stderr.decode()}")
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
                str(Path(output_path).resolve()),
            ]
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg add_audio failed: {stderr.decode() if stderr else 'Unknown error'}")
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
    async def stretch_to_duration(
        input_path: str,
        target_duration: float,
        output_path: str,
    ) -> str:
        """Stretch a video clip to match *target_duration*.

        If the clip is shorter than *target_duration* it is looped
        (seamlessly via ``stream_loop``).  If it is longer it is
        truncated.  The output is re-encoded to ensure a clean loop
        boundary.
        """
        clip_duration = await VideoProcessor.get_duration(input_path)
        if clip_duration <= 0:
            raise RuntimeError(f"Cannot determine duration of {input_path}")

        if clip_duration >= target_duration - 0.1:
            # Clip is long enough — just trim
            cmd = [
                "ffmpeg", "-i", input_path,
                "-t", str(target_duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac",
                "-y", str(Path(output_path).resolve()),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg trim failed: {stderr.decode()}")
            return output_path

        # Loop the clip to fill the target duration
        # Use -stream_loop -1 (infinite loop) + -t to stop at target
        loops_needed = int(target_duration / clip_duration) + 1

        # Build concat list for precise looping
        list_file = Path(output_path).parent / f"loop_{Path(input_path).stem}.txt"
        with open(list_file, "w") as f:
            for _ in range(loops_needed):
                f.write(f"file '{input_path}'\n")

        cmd = [
            "ffmpeg",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-y", str(Path(output_path).resolve()),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        list_file.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg loop-stretch failed: {stderr.decode()}")
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

    @staticmethod
    async def generate_thumbnail(
        video_path: str,
        output_path: str,
        timestamp: float = 0.0,
        width: int = 320,
        height: int = 180,
    ) -> str:
        """Generate a thumbnail image from a video."""
        cmd = [
            "ffmpeg",
            "-ss",
            str(timestamp),
            "-i",
            video_path,
            "-vframes",
            "1",
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
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
    async def generate_thumbnails(
        video_path: str,
        output_dir: str,
        count: int = 5,
        width: int = 320,
        height: int = 180,
    ) -> list[str]:
        """Generate multiple thumbnails evenly distributed through the video."""
        duration = await VideoProcessor.get_duration(video_path)
        interval = duration / (count + 1)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        thumbnails = []
        for i in range(count):
            timestamp = interval * (i + 1)
            thumb_path = str(output_path / f"thumb_{i:03d}.jpg")
            await VideoProcessor.generate_thumbnail(
                video_path, thumb_path, timestamp, width, height
            )
            if Path(thumb_path).exists():
                thumbnails.append(thumb_path)

        return thumbnails

    @staticmethod
    async def create_sprite_sheet(
        video_path: str,
        output_path: str,
        columns: int = 5,
        rows: int = 5,
        thumb_width: int = 160,
        thumb_height: int = 90,
    ) -> str:
        """Create a sprite sheet of thumbnails for video scrubbing preview."""

        duration = await VideoProcessor.get_duration(video_path)
        count = columns * rows
        interval = duration / (count + 1)

        temp_dir = Path(output_path).parent / "temp_thumbs"
        temp_dir.mkdir(parents=True, exist_ok=True)

        thumbnails = []
        for i in range(count):
            timestamp = interval * (i + 1)
            thumb_path = str(temp_dir / f"thumb_{i:03d}.jpg")
            await VideoProcessor.generate_thumbnail(
                video_path, thumb_path, timestamp, thumb_width, thumb_height
            )
            if Path(thumb_path).exists():
                thumbnails.append(thumb_path)

        total_width = thumb_width * columns
        total_height = thumb_height * ((len(thumbnails) + columns - 1) // columns)

        filter_parts = []
        for i, thumb in enumerate(thumbnails):
            col = i % columns
            row = i // columns
            x = col * thumb_width
            y = row * thumb_height
            filter_parts.append(
                f"[{i}:v]setpts=PTS-STARTPTS,drawbox=x={x}:y={y}:w={thumb_width}:h={thumb_height}:color=black:t=fill"
            )

        inputs = []
        for thumb in thumbnails:
            inputs.extend(["-i", thumb])

        filter_complex = "; ".join(filter_parts) if filter_parts else ""

        cmd = [
            "ffmpeg",
            *inputs,
            "-filter_complex",
            f"{''.join(f'[{i}:v]' for i in range(len(thumbnails)))}xstack=inputs={len(thumbnails)}:layout=",
            "-y",
            output_path,
        ]

        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={total_width}x{total_height}:d=0.04",
        ]

        for thumb in thumbnails:
            cmd.extend(["-i", thumb])

        overlay_parts = []
        for i, thumb in enumerate(thumbnails):
            col = i % columns
            row = i // columns
            x = col * thumb_width
            y = row * thumb_height
            overlay_parts.append(f"[0:v][{i + 1}:v]overlay={x}:{y}")

        filter_complex = ",".join(overlay_parts) if overlay_parts else "null"

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-frames:v",
                "1",
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

        for thumb in thumbnails:
            Path(thumb).unlink(missing_ok=True)
        temp_dir.rmdir()

        return output_path

    @staticmethod
    async def validate_video_output(
        video_path: str,
        expected_duration: float,
        fps: float = 16.0,
        min_threshold: float = 0.8,
    ) -> ValidationResult:
        """Validate a generated video has the expected frame count and duration.

        Uses an 80% threshold by default to tolerate codec rounding (e.g. a 5s
        clip at 16fps may encode to 78-82 frames instead of exactly 80) while
        still catching severely truncated output (e.g. Wan 2.2 producing a
        single-frame clip).
        """
        expected_frames = int(expected_duration * fps)
        min_frames = max(1, int(expected_frames * min_threshold))
        min_duration = expected_duration * min_threshold

        if not Path(video_path).exists():
            return ValidationResult(
                valid=False,
                actual_frames=0,
                actual_duration=0.0,
                expected_frames=expected_frames,
                error_message=f"Video file not found: {video_path}",
            )

        try:
            info = await VideoProcessor.get_video_info(video_path)
        except FileNotFoundError:
            return ValidationResult(
                valid=False,
                actual_frames=0,
                actual_duration=0.0,
                expected_frames=expected_frames,
                error_message="ffprobe binary not found on PATH",
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                actual_frames=0,
                actual_duration=0.0,
                expected_frames=expected_frames,
                error_message=f"Failed to probe video: {e}",
            )

        streams = info.get("streams") or []
        video_stream = next(
            (s for s in streams if s.get("codec_type") == "video"),
            None,
        )
        if video_stream is None:
            return ValidationResult(
                valid=False,
                actual_frames=0,
                actual_duration=0.0,
                expected_frames=expected_frames,
                error_message="No video stream found in file (file may be corrupted)",
            )

        codec_name = video_stream.get("codec_name") or ""
        if not codec_name or codec_name in ("null", "unknown", "N/A"):
            return ValidationResult(
                valid=False,
                actual_frames=0,
                actual_duration=0.0,
                expected_frames=expected_frames,
                error_message=f"Invalid video codec: {codec_name!r}",
            )

        raw_duration = video_stream.get("duration") or info.get("format", {}).get("duration")
        try:
            actual_duration = float(raw_duration) if raw_duration else 0.0
        except (TypeError, ValueError):
            actual_duration = 0.0

        nb_frames_raw = video_stream.get("nb_frames")
        if nb_frames_raw not in (None, "", "N/A"):
            try:
                actual_frames = int(nb_frames_raw)
            except (TypeError, ValueError):
                actual_frames = int(actual_duration * fps)
        else:
            actual_frames = int(actual_duration * fps)

        if actual_frames < min_frames:
            return ValidationResult(
                valid=False,
                actual_frames=actual_frames,
                actual_duration=actual_duration,
                expected_frames=expected_frames,
                error_message=(
                    f"Video has only {actual_frames} frame(s), "
                    f"expected ~{expected_frames} frames for "
                    f"{expected_duration:.1f}s at {fps}fps (minimum {min_frames})"
                ),
            )

        if actual_duration < min_duration:
            return ValidationResult(
                valid=False,
                actual_frames=actual_frames,
                actual_duration=actual_duration,
                expected_frames=expected_frames,
                error_message=(
                    f"Video duration is {actual_duration:.2f}s, "
                    f"expected at least {min_duration:.2f}s "
                    f"for target {expected_duration:.1f}s"
                ),
            )

        return ValidationResult(
            valid=True,
            actual_frames=actual_frames,
            actual_duration=actual_duration,
            expected_frames=expected_frames,
            error_message=None,
        )
