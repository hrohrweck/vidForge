"""Auto-import service for job outputs into media library"""

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import MediaAsset, MediaFolder
from app.services.media_metadata import probe_audio, probe_image, probe_video
from app.services.preview_generator import extract_first_frame

logger = logging.getLogger(__name__)


async def auto_import_job_outputs(
    job_id: UUID,
    user_id: UUID,
    job_name: str,
    db: AsyncSession,
    project_id: UUID | None = None,
) -> list[MediaAsset]:
    """Auto-import job outputs into the media library.

    Creates assets in a /Jobs/{job_name}/ folder for:
    - final.mp4 (video)
    - preview.mp4 (video)
    - scene videos (video)
    - scene images (image)
    - storyboard.md (markdown)

    Returns list of created MediaAsset objects.
    """
    from app.database import Job

    # Get job details
    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        logger.warning(f"Job {job_id} not found for auto-import")
        return []

    # Create or get the Jobs folder
    jobs_folder = await _get_or_create_folder(
        user_id=user_id,
        name="Jobs",
        parent_id=None,
        db=db,
    )

    # Create or get the job-specific folder
    job_folder_name = job_name or f"Job-{str(job_id)[:8]}"
    job_folder = await _get_or_create_folder(
        user_id=user_id,
        name=job_folder_name,
        parent_id=jobs_folder.id,
        db=db,
    )

    created_assets = []

    # Import final video
    if job.output_path:
        final_path = Path(job.output_path)
        if final_path.exists():
            asset = await _create_asset_from_file(
                user_id=user_id,
                folder_id=job_folder.id,
                file_path=final_path,
                name="final.mp4",
                file_type="video",
                source_job_id=job_id,
                db=db,
                project_id=project_id,
            )
            if asset:
                created_assets.append(asset)

    # Import preview video
    if job.preview_path:
        preview_path = Path(job.preview_path)
        if preview_path.exists():
            asset = await _create_asset_from_file(
                user_id=user_id,
                folder_id=job_folder.id,
                file_path=preview_path,
                name="preview.mp4",
                file_type="video",
                source_job_id=job_id,
                db=db,
                project_id=project_id,
            )
            if asset:
                created_assets.append(asset)

    # Import scene outputs if available
    from app.database import VideoScene
    scenes_result = await db.execute(
        select(VideoScene).where(VideoScene.job_id == job_id)
    )
    scenes = scenes_result.scalars().all()

    for i, scene in enumerate(scenes):
        # Import scene image
        if scene.image_path:
            image_path = Path(scene.image_path)
            if image_path.exists():
                asset = await _create_asset_from_file(
                    user_id=user_id,
                    folder_id=job_folder.id,
                    file_path=image_path,
                    name=f"scene-{i+1}-image.png",
                    file_type="image",
                    source_job_id=job_id,
                    db=db,
                    project_id=project_id,
                )
                if asset:
                    created_assets.append(asset)

        # Import scene video
        if scene.video_path:
            video_path = Path(scene.video_path)
            if video_path.exists():
                asset = await _create_asset_from_file(
                    user_id=user_id,
                    folder_id=job_folder.id,
                    file_path=video_path,
                    name=f"scene-{i+1}-video.mp4",
                    file_type="video",
                    source_job_id=job_id,
                    db=db,
                    project_id=project_id,
                )
                if asset:
                    created_assets.append(asset)

    logger.info(f"Auto-imported {len(created_assets)} assets for job {job_id}")
    return created_assets


async def _get_or_create_folder(
    user_id: UUID,
    name: str,
    parent_id: UUID | None,
    db: AsyncSession,
) -> MediaFolder:
    """Get or create a folder."""
    from sqlalchemy import select

    result = await db.execute(
        select(MediaFolder).where(
            MediaFolder.user_id == user_id,
            MediaFolder.parent_id == parent_id,
            MediaFolder.name == name,
        )
    )
    folder = result.scalar_one_or_none()

    if folder:
        return folder

    folder = MediaFolder(
        user_id=user_id,
        parent_id=parent_id,
        name=name,
    )
    db.add(folder)
    await db.flush()

    return folder


async def _create_asset_from_file(
    user_id: UUID,
    folder_id: UUID,
    file_path: Path,
    name: str,
    file_type: str,
    source_job_id: UUID,
    db: AsyncSession,
    project_id: UUID | None = None,
) -> MediaAsset | None:
    """Create a MediaAsset from an existing file."""
    try:
        logger.info(f"_create_asset_from_file: user_id={user_id}, folder_id={folder_id}, file={file_path}, name={name}")

        if not file_path.exists():
            logger.error(f"File does not exist: {file_path}")
            return None

        file_size = file_path.stat().st_size
        logger.info(f"File exists, size: {file_size} bytes")

        asset = MediaAsset(
            user_id=user_id,
            folder_id=folder_id,
            project_id=project_id,
            name=name,
            file_path=str(file_path),
            file_type=file_type,
            mime_type=_get_mime_type(file_path),
            size_bytes=file_size,
            source_type="generated",
            source_job_id=source_job_id,
        )
        if file_type == "image":
            asset.asset_metadata = probe_image(file_path)
        elif file_type == "video":
            asset.asset_metadata = probe_video(file_path)
        elif file_type == "audio":
            asset.asset_metadata = probe_audio(file_path)

        db.add(asset)
        await db.flush()
        logger.info(f"MediaAsset added to DB, id={asset.id}")

        # Generate preview for videos
        if file_type == "video":
            preview_path = await extract_first_frame(file_path, user_id, asset.id)
            if preview_path:
                asset.preview_path = str(preview_path)

        await db.flush()
        logger.info(f"MediaAsset created successfully: {asset.id}")
        return asset

    except Exception as e:
        import traceback
        logger.error(f"Failed to create asset for {file_path}: {e}\n{traceback.format_exc()}")
        return None


def _get_mime_type(file_path: Path) -> str:
    """Get MIME type from file extension."""
    import mimetypes
    mime_type = mimetypes.guess_type(str(file_path))[0]
    return mime_type or "application/octet-stream"
