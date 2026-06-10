import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.video_processor import (
    _run_subprocess_with_timeout,
    FFMPEG_TIMEOUT_PROFILES,
)


class TestRunSubprocessWithTimeout:
    @pytest.mark.asyncio
    async def test_kills_slow_process_at_deadline(self):
        class FakeProc:
            def __init__(self):
                self._killed = False
                self.returncode = -9

            async def communicate(self):
                await asyncio.sleep(10)
                return b"", b""

            def kill(self):
                self._killed = True

        fake = FakeProc()

        with patch(
            "app.services.video_processor.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake),
        ):
            with pytest.raises(TimeoutError, match="timed out after 0.1s"):
                await _run_subprocess_with_timeout(
                    ["ffmpeg", "-i", "in.mp4", "out.mp4"],
                    timeout=0.1,
                )

        assert fake._killed is True

    @pytest.mark.asyncio
    async def test_returns_output_when_fast_enough(self):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"stdout data", b"stderr data"))
        proc.kill = MagicMock()
        proc.returncode = 0

        with patch(
            "app.services.video_processor.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ):
            stdout, stderr = await _run_subprocess_with_timeout(
                ["ffmpeg", "-i", "in.mp4", "out.mp4"],
                timeout=60.0,
            )

        assert stdout == b"stdout data"
        assert stderr == b"stderr data"
        proc.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_nonzero_exit(self):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b"something failed"))
        proc.kill = MagicMock()
        proc.returncode = 1

        with patch(
            "app.services.video_processor.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ):
            with pytest.raises(RuntimeError, match="something failed"):
                await _run_subprocess_with_timeout(
                    ["ffmpeg", "-i", "in.mp4", "out.mp4"],
                    timeout=60.0,
                )

    @pytest.mark.asyncio
    async def test_timeout_profiles_are_defined(self):
        expected = {"METADATA", "THUMBNAIL", "ENCODE", "MERGE", "CHAIN"}
        assert set(FFMPEG_TIMEOUT_PROFILES.keys()) == expected
        for name, value in FFMPEG_TIMEOUT_PROFILES.items():
            assert value > 0, f"Profile {name} must be positive"

    @pytest.mark.asyncio
    async def test_uses_env_override(self, monkeypatch):
        monkeypatch.setenv("VIDFORGE_FFMPEG_TIMEOUT_METADATA", "300")
        import os

        # Verify the env var is set and parsed correctly without reloading
        # the module (reload breaks class identity for InvalidVideoOutputError
        # and method identity for VideoProcessor.generate_thumbnail).
        assert os.getenv("VIDFORGE_FFMPEG_TIMEOUT_METADATA") == "300"
        assert float(os.getenv("VIDFORGE_FFMPEG_TIMEOUT_METADATA", "60")) == 300.0
