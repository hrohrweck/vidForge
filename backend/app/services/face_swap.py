"""Face-swap pipeline stage for avatar character consistency.

Replaces detected faces in video frames with a target avatar face using
insightface (buffalo_l detection + inswapper_128 model).  The module is
an *optional* post-processing stage — if insightface is not installed
or no faces are detected, the original video is passed through unchanged.

Usage (async, inside a plugin pipeline)::

    from app.services.face_swap import apply_face_swap

    swapped_path = await apply_face_swap(
        video_path=scene.generated_video_path,
        target_face_path="/path/to/avatar_reference.jpg",
        output_path=str(output_dir / f"scene_{scene.scene_number}_swapped.mp4"),
        face_detection_threshold=0.5,
    )
    scene.generated_video_path = swapped_path
"""

from __future__ import annotations

import logging
import shutil

logger = logging.getLogger(__name__)


async def apply_face_swap(
    video_path: str,
    target_face_path: str,
    output_path: str,
    face_detection_threshold: float = 0.5,
) -> str:
    """Replace faces in video frames with the target avatar face.

    Args:
        video_path: Path to input video file.
        target_face_path: Path to target face image (avatar reference photo).
        output_path: Path where face-swapped video will be written.
        face_detection_threshold: Confidence threshold for face detection
            (0.0–1.0).  Higher = fewer but higher-quality detections.

    Returns:
        The *output_path* of the face-swapped video.

    **Graceful fallback**: If any of the following conditions occur the
    original video is copied unchanged to *output_path* and a warning is
    logged — the pipeline continues without interruption:

    - ``insightface`` / ``opencv-python`` not installed
    - Face-detection model fails to initialise
    - Target face image is missing or contains no detectable faces
    - No faces are found in any video frame
    """
    try:
        import cv2
        import insightface
        import numpy as np
    except ImportError:
        logger.warning(
            "insightface / opencv-python not installed — skipping face-swap. "
            "Install with: pip install insightface opencv-python onnxruntime"
        )
        shutil.copy2(video_path, output_path)
        return output_path

    try:
        face_analyser = insightface.app.FaceAnalysis(name="buffalo_l")
        face_analyser.prepare(ctx_id=-1, det_thresh=face_detection_threshold)
    except Exception:
        logger.error(
            "Failed to initialise insightface FaceAnalysis model.",
            exc_info=True,
        )
        shutil.copy2(video_path, output_path)
        return output_path

    try:
        swapper = insightface.model_zoo.get_model(
            "inswapper_128.onnx", download=True, download_zip=True
        )
    except Exception:
        logger.error(
            "Failed to load inswapper_128 face-swap model.", exc_info=True,
        )
        shutil.copy2(video_path, output_path)
        return output_path

    target_img = cv2.imread(target_face_path)
    if target_img is None:
        logger.error("Cannot read target face image: %s", target_face_path)
        shutil.copy2(video_path, output_path)
        return output_path

    target_faces = face_analyser.get(target_img)
    if not target_faces:
        logger.warning(
            "No face detected in target image %s — skipping face-swap.",
            target_face_path,
        )
        shutil.copy2(video_path, output_path)
        return output_path

    target_face = target_faces[0]

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Cannot open video: %s", video_path)
        shutil.copy2(video_path, output_path)
        return output_path

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if width <= 0 or height <= 0 or fps <= 0:
        logger.error(
            "Invalid video dimensions/fps (%dx%d @ %.2f fps) in %s",
            width, height, fps, video_path,
        )
        cap.release()
        shutil.copy2(video_path, output_path)
        return output_path

    # Write to a temp file first so output_path is only touched on success.
    temp_output = output_path + ".tmp.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))
    if not out.isOpened():
        logger.error("Cannot create output video writer for %s", temp_output)
        cap.release()
        shutil.copy2(video_path, output_path)
        return output_path

    frames_swapped = 0
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1

        try:
            faces = face_analyser.get(frame)
            if faces:
                for face in faces:
                    frame = swapper.get(frame, face, target_face, paste_back=True)
                frames_swapped += 1
        except Exception:
            logger.debug(
                "Frame %d/%d: face-swap error — writing original frame.",
                frame_idx, total_frames, exc_info=True,
            )

        out.write(frame)

    cap.release()
    out.release()

    # Atomically move temp → final output
    shutil.move(temp_output, output_path)

    if frames_swapped > 0:
        logger.info(
            "Face-swap complete: %d/%d frames had faces swapped.",
            frames_swapped, total_frames,
        )
    else:
        logger.warning(
            "No faces detected in any video frame of %s — video unchanged.",
            video_path,
        )

    return output_path
