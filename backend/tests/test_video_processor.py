import subprocess
from pathlib import Path

import pytest

from app.services.video_processor import VideoProcessor


class TestValidateVideoOutput:
    """Tests for VideoProcessor.validate_video_output() using real ffmpeg/ffprobe."""

    def _create_test_video(self, path: Path, duration: float, fps: float = 16.0) -> None:
        """Create a test video with ffmpeg using the testsrc filter."""
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size=320x240:rate={fps}",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            str(path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def _create_single_frame_video(self, path: Path) -> None:
        """Create a video with exactly 1 frame."""
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=0.001:size=320x240:rate=16",
            "-frames:v", "1",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            str(path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    @pytest.mark.asyncio
    async def test_validate_video_output_passes(self, tmp_path: Path):
        """A 5-second video at 16fps should pass validation."""
        video_path = tmp_path / "test_5s.mp4"
        self._create_test_video(video_path, duration=5.0, fps=16.0)

        result = await VideoProcessor.validate_video_output(
            str(video_path), expected_duration=5.0, fps=16.0
        )

        assert result.valid is True
        assert result.expected_frames == 80
        # Allow small variance due to codec rounding
        assert 75 <= result.actual_frames <= 85
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_validate_video_output_fails_one_frame(self, tmp_path: Path):
        """A 1-frame video should fail validation and mention the bug scenario."""
        video_path = tmp_path / "test_1frame.mp4"
        self._create_single_frame_video(video_path)

        result = await VideoProcessor.validate_video_output(
            str(video_path), expected_duration=5.0, fps=16.0
        )

        assert result.valid is False
        assert result.actual_frames == 1
        assert "1 frame" in result.error_message
        assert "expected ~80" in result.error_message

    @pytest.mark.asyncio
    async def test_validate_video_output_fails_zero_bytes(self, tmp_path: Path):
        """An empty file should fail validation."""
        video_path = tmp_path / "empty.mp4"
        video_path.write_bytes(b"")

        result = await VideoProcessor.validate_video_output(
            str(video_path), expected_duration=5.0, fps=16.0
        )

        assert result.valid is False
        assert "No video stream found" in result.error_message

    @pytest.mark.asyncio
    async def test_validate_video_output_fails_corrupted(self, tmp_path: Path):
        """A non-video file renamed to .mp4 should fail validation."""
        video_path = tmp_path / "fake.mp4"
        video_path.write_text("this is not a video file")

        result = await VideoProcessor.validate_video_output(
            str(video_path), expected_duration=5.0, fps=16.0
        )

        assert result.valid is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_validate_video_output_handles_missing_file(self, tmp_path: Path):
        """A non-existent file should fail validation gracefully."""
        video_path = tmp_path / "does_not_exist.mp4"

        result = await VideoProcessor.validate_video_output(
            str(video_path), expected_duration=5.0, fps=16.0
        )

        assert result.valid is False
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_validate_video_output_80_percent_threshold(self, tmp_path: Path):
        """A 4-second video (64 frames) at 16fps should pass at exactly 80% threshold."""
        video_path = tmp_path / "test_4s.mp4"
        self._create_test_video(video_path, duration=4.0, fps=16.0)

        result = await VideoProcessor.validate_video_output(
            str(video_path), expected_duration=5.0, fps=16.0
        )

        assert result.valid is True
        assert result.expected_frames == 80
        # 4s * 16fps = 64 frames (exactly 80% of 80)
        assert result.actual_frames >= 60

    @pytest.mark.asyncio
    async def test_validate_video_output_below_threshold(self, tmp_path: Path):
        """A 3.9-second video (62 frames) at 16fps should fail below 80% threshold."""
        video_path = tmp_path / "test_3_9s.mp4"
        self._create_test_video(video_path, duration=3.9, fps=16.0)

        result = await VideoProcessor.validate_video_output(
            str(video_path), expected_duration=5.0, fps=16.0
        )

        assert result.valid is False
        assert result.expected_frames == 80
        # 3.9s * 16fps = 62.4 frames, which is 78% of 80 — below threshold
        assert result.actual_frames < 64
        assert "expected ~80" in result.error_message
