"""FFmpeg preview frame extraction service"""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from app.services.media_path import get_preview_path

logger = logging.getLogger(__name__)


async def extract_preview_frame(
    video_path: Path,
    user_id: UUID,
    asset_id: UUID,
    timestamp_seconds: float = 0.0,
    output_filename: str = "preview.jpg",
) -> Path | None:
    """Extract a single frame from a video at the given timestamp.

    Args:
        video_path: Path to the video file
        user_id: User ID for storage path
        asset_id: Asset ID for storage path
        timestamp_seconds: Timestamp to extract frame from (default 0 = first frame)
        output_filename: Output filename for the preview

    Returns:
        Path to the generated preview image, or None if extraction failed
    """
    preview_path = get_preview_path(user_id, asset_id, output_filename)

    # Ensure video path is absolute
    video_path = Path(video_path).resolve()

    if not video_path.exists():
        logger.error(f"Video file not found: {video_path}")
        return None

    # FFmpeg command to extract single frame
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-ss", str(timestamp_seconds),  # Seek to timestamp
        "-i", str(video_path),  # Input file
        "-vframes", "1",  # Extract 1 frame
        "-q:v", "2",  # Quality (2 = high)
        "-vf", "scale=480:-1",  # Scale width to 480px, maintain aspect ratio
        str(preview_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"FFmpeg preview extraction failed: {stderr.decode()}")
            return None

        if not preview_path.exists():
            logger.error("Preview file was not created")
            return None

        logger.info(f"Preview extracted: {preview_path}")
        return preview_path

    except Exception as e:
        logger.error(f"Preview extraction error: {e}")
        return None


async def extract_first_frame(
    video_path: Path,
    user_id: UUID,
    asset_id: UUID,
) -> Path | None:
    """Extract the first frame of a video (convenience wrapper)."""
    return await extract_preview_frame(video_path, user_id, asset_id, timestamp_seconds=0.0)


async def get_video_duration(video_path: Path) -> float | None:
    """Get video duration in seconds using ffprobe.

    Args:
        video_path: Path to the video file

    Returns:
        Duration in seconds, or None if failed
    """
    video_path = Path(video_path).resolve()

    if not video_path.exists():
        return None

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"ffprobe failed: {stderr.decode()}")
            return None

        duration = float(stdout.decode().strip())
        return duration

    except Exception as e:
        logger.error(f"Duration check error: {e}")
        return None
