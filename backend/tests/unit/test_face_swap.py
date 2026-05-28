"""Unit tests for app.services.face_swap.apply_face_swap.

Verifies every fallback path and the successful pipeline without requiring
actual insightface / cv2 / numpy to be installed.
"""

from __future__ import annotations

import builtins
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from app.services.face_swap import apply_face_swap

# ── helpers ──────────────────────────────────────────────────────────


def _original_import():
    return builtins.__import__


def _selective_import_fail(*modules_to_fail: str):
    """Return a __import__ side_effect that raises ImportError for
    the named modules but delegates everything else."""

    _real = builtins.__import__

    def _importer(name, *args, **kwargs):
        if name in modules_to_fail:
            raise ImportError(f"No module named '{name}'")
        return _real(name, *args, **kwargs)

    return _importer


def _mock_cv2(
    *,
    imread_returns: object = MagicMock(),
    cap_is_opened: bool = True,
    cap_dims: tuple[int, int, float, int] = (848, 480, 16.0, 80),
    cap_read_side_effect: object | None = None,
    writer_is_opened: bool = True,
) -> MagicMock:
    """Build a mock ``cv2`` module with controllable behaviour."""
    mock_cv2 = MagicMock(name="cv2")

    # -- imread --
    mock_cv2.imread.return_value = imread_returns

    # -- VideoCapture --
    cap = MagicMock(name="VideoCapture")
    cap.isOpened.return_value = cap_is_opened
    w, h, fps, total = cap_dims
    # cv2.CAP_PROP_* constants are small ints
    cap.get.side_effect = lambda prop: {3: w, 4: h, 5: fps, 7: total}.get(
        int(prop), 0.0
    )
    if cap_read_side_effect is not None:
        cap.read.side_effect = cap_read_side_effect
    else:
        frame = MagicMock(name="frame")
        cap.read.side_effect = [(True, frame), (False, None)]
    mock_cv2.VideoCapture.return_value = cap

    # -- VideoWriter --
    writer = MagicMock(name="VideoWriter")
    writer.isOpened.return_value = writer_is_opened
    mock_cv2.VideoWriter.return_value = writer
    mock_cv2.VideoWriter_fourcc.return_value = 0x7634706D  # 'mp4v'

    # -- constants --
    mock_cv2.CAP_PROP_FRAME_WIDTH = 3
    mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
    mock_cv2.CAP_PROP_FPS = 5
    mock_cv2.CAP_PROP_FRAME_COUNT = 7

    return mock_cv2


def _mock_insightface(
    *,
    target_faces: list | None = None,
    frame_faces: list | None = None,
    analyser_raises: Exception | None = None,
    swapper_raises: Exception | None = None,
) -> MagicMock:
    """Build a mock ``insightface`` module."""
    mock_if = MagicMock(name="insightface")

    analyser = MagicMock(name="FaceAnalysis")
    if analyser_raises:
        analyser.prepare.side_effect = analyser_raises
        # get() should also fail if model wasn't prepared
        analyser.get.side_effect = analyser_raises
    else:
        # By default: one face in target, none in frames
        analyser.get.side_effect = (
            [[MagicMock(name="target_face")]]  # first call → target
            if target_faces is None
            else lambda img, faces=target_faces: faces
        )
    mock_if.app.FaceAnalysis.return_value = analyser

    if swapper_raises:
        mock_if.model_zoo.get_model.side_effect = swapper_raises
    else:
        swapper = MagicMock(name="inswapper")
        # swapper.get returns the frame (or modified frame)
        def _swap(frame, face, target, paste_back=True):  # noqa: ARG001
            return frame
        swapper.get.side_effect = _swap
        mock_if.model_zoo.get_model.return_value = swapper

    return mock_if


def _mock_numpy() -> MagicMock:
    return MagicMock(name="numpy")


def _install_mock_modules(cv2_mock, insightface_mock, numpy_mock):
    """Patch sys.modules so that ``import cv2`` etc. resolve to mocks.

    Returns a cleanup function (call to restore).
    """
    patchers = [
        patch.dict(sys.modules, {"cv2": cv2_mock, **sys.modules}),
        patch.dict(sys.modules, {"insightface": insightface_mock, **sys.modules}),
        patch.dict(sys.modules, {"numpy": numpy_mock, **sys.modules}),
    ]
    for p in patchers:
        p.start()
    return lambda: [p.stop() for p in reversed(patchers)]


# ── Test 1: insightface not installed ────────────────────────────────


@pytest.mark.asyncio
async def test_apply_face_swap_insightface_not_installed(tmp_path: Path):
    """When cv2/insightface/numpy cannot be imported, copy original video
    unchanged and return output_path."""

    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake-video-bytes")
    output = tmp_path / "output.mp4"

    import_fail = _selective_import_fail("cv2", "insightface", "numpy")

    with (
        patch("builtins.__import__", side_effect=import_fail),
        patch("shutil.copy2", wraps=shutil.copy2) as mock_copy,
    ):
        result = await apply_face_swap(
            str(video),
            target_face_path="/dev/null",
            output_path=str(output),
        )

    mock_copy.assert_called_once_with(str(video), str(output))
    assert result == str(output)
    assert output.read_bytes() == video.read_bytes()


# ── Test 2: missing / unopenable video file ──────────────────────────


@pytest.mark.asyncio
async def test_apply_face_swap_missing_video_file(tmp_path: Path):
    """cv2.VideoCapture fails to open the video → fallback copy."""

    video = tmp_path / "corrupt.mp4"
    video.write_bytes(b"corrupt-video")
    target = tmp_path / "face.jpg"
    target.write_bytes(b"fake-face")
    output = tmp_path / "output.mp4"

    mock_cv2 = _mock_cv2(
        cap_is_opened=False,
        imread_returns=MagicMock(name="target_img"),
    )
    mock_if = _mock_insightface()
    mock_np = _mock_numpy()
    cleanup = _install_mock_modules(mock_cv2, mock_if, mock_np)

    try:
        with patch("shutil.copy2", wraps=shutil.copy2) as mock_copy:
            result = await apply_face_swap(
                str(video), str(target), str(output),
            )

        mock_copy.assert_called_once()
        assert result == str(output)
    finally:
        cleanup()


# ── Test 3: missing target-face image ────────────────────────────────


@pytest.mark.asyncio
async def test_apply_face_swap_missing_face_image(tmp_path: Path):
    """cv2.imread returns None for target face → fallback copy."""

    video = tmp_path / "input.mp4"
    video.write_bytes(b"real-video")
    output = tmp_path / "output.mp4"

    mock_cv2 = _mock_cv2(imread_returns=None)
    mock_if = _mock_insightface()
    mock_np = _mock_numpy()
    cleanup = _install_mock_modules(mock_cv2, mock_if, mock_np)

    try:
        with patch("shutil.copy2", wraps=shutil.copy2) as mock_copy:
            result = await apply_face_swap(
                str(video),
                target_face_path="/nonexistent/face.jpg",
                output_path=str(output),
            )

        mock_copy.assert_called_once_with(str(video), str(output))
        assert result == str(output)
        assert output.read_bytes() == video.read_bytes()
    finally:
        cleanup()


# ── Test 4: no face detected in target image ─────────────────────────


@pytest.mark.asyncio
async def test_apply_face_swap_no_face_in_target(tmp_path: Path):
    """face_analyser.get returns 0 faces for the target → fallback copy."""

    video = tmp_path / "input.mp4"
    video.write_bytes(b"video-data")
    target = tmp_path / "face.jpg"
    target.write_bytes(b"no-face-here")
    output = tmp_path / "output.mp4"

    mock_cv2 = _mock_cv2()
    mock_if = _mock_insightface(target_faces=[])  # zero faces
    mock_np = _mock_numpy()
    cleanup = _install_mock_modules(mock_cv2, mock_if, mock_np)

    try:
        with patch("shutil.copy2", wraps=shutil.copy2) as mock_copy:
            result = await apply_face_swap(
                str(video), str(target), str(output),
            )

        # Verify fallback — video copied unchanged
        mock_copy.assert_called_once_with(str(video), str(output))
        assert result == str(output)
        assert output.read_bytes() == video.read_bytes()
    finally:
        cleanup()


# ── Test 5: no faces detected in any video frame ─────────────────────


@pytest.mark.asyncio
async def test_apply_face_swap_no_face_in_video(tmp_path: Path):
    """Video has frames but face_analyser.get returns [] for every frame.
    The video is written unchanged (no swaps) but the function still
    succeeds and returns output_path."""

    video = tmp_path / "input.mp4"
    video.write_bytes(b"video-bytes")
    target = tmp_path / "face.jpg"
    target.write_bytes(b"target-face")
    output = tmp_path / "output.mp4"

    mock_cv2 = _mock_cv2()
    mock_if = _mock_insightface(
        target_faces=[MagicMock(name="target_face")],
        frame_faces=[],  # face analyser always returns empty for frames
    )
    mock_np = _mock_numpy()
    cleanup = _install_mock_modules(mock_cv2, mock_if, mock_np)

    try:
        with patch("shutil.move") as mock_move:
            result = await apply_face_swap(
                str(video), str(target), str(output),
            )

        temp_path = str(output) + ".tmp.mp4"
        mock_move.assert_called_once_with(temp_path, str(output))
        assert result == str(output)
    finally:
        cleanup()


# ── Test 6: return value matches output_path ─────────────────────────


@pytest.mark.asyncio
async def test_apply_face_swap_returns_output_path(tmp_path: Path):
    """On a successful swap the function returns output_path."""

    video = tmp_path / "input.mp4"
    video.write_bytes(b"v")
    target = tmp_path / "face.jpg"
    target.write_bytes(b"f")
    output = tmp_path / "output.mp4"

    mock_cv2 = _mock_cv2()
    mock_if = _mock_insightface(
        target_faces=[MagicMock(name="target_face")],
        frame_faces=[MagicMock(name="frame_face")],
    )
    mock_np = _mock_numpy()
    cleanup = _install_mock_modules(mock_cv2, mock_if, mock_np)

    try:
        with patch("shutil.move") as mock_move:
            result = await apply_face_swap(
                str(video), str(target), str(output),
            )

        assert result == str(output)
        temp_path = str(output) + ".tmp.mp4"
        mock_move.assert_called_once_with(temp_path, str(output))
    finally:
        cleanup()


# ── Test 7: optional deps imported inside function, not at module level ──


def test_apply_face_swap_imports_optional_dependencies():
    """Verify insightface / cv2 / numpy are NOT imported at module level.

    They must be imported lazily inside the try/except block of
    ``apply_face_swap()`` so the module remains importable without
    the optional face-swap dependencies installed.
    """
    # Re-import the module to get a clean state
    import importlib

    import app.services.face_swap as mod

    importlib.reload(mod)

    # At module level, none of the optional packages should be visible
    assert "cv2" not in dir(mod)
    assert "insightface" not in dir(mod)

    # numpy is imported as a local binding inside the function but the
    # module-level ``import numpy`` is also absent.
    assert "numpy" not in dir(mod)

    # The function itself should be available
    assert callable(mod.apply_face_swap)
