"""
Plugin-aware job dispatcher.

Replaces the hardcoded stage functions with a generic dispatcher that
looks up the template's plugin and calls the corresponding method.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, Template, VideoScene
from app.plugins.registry import get_plugin, get_plugin_for_template
from app.services.media_events import record_and_publish_media_event
from app.workers.context import ctx

logger = logging.getLogger(__name__)


async def _load_job(db: AsyncSession, job_id: str) -> tuple[Job, Any]:
    """Load a job and resolve its plugin.

    Returns ``(job, plugin)``.  Raises ``ValueError`` if the job or
    plugin cannot be found.
    """
    job_uuid = UUID(job_id)
    result = await db.execute(select(Job).where(Job.id == job_uuid))
    job = result.scalar_one_or_none()
    if not job:
        raise ValueError(f"Job {job_id} not found")

    plugin = None

    # Try plugin_id from template config
    if job.template_id:
        tresult = await db.execute(select(Template).where(Template.id == job.template_id))
        template = tresult.scalar_one_or_none()
        if template and template.config:
            pid = template.config.get("plugin_id")
            if pid:
                plugin = get_plugin(pid)
            if not plugin:
                plugin = get_plugin_for_template(template.config)

    # Fallback: infer from workflow_type
    if not plugin:
        wf = job.workflow_type or ""
        if wf == "scene_based":
            plugin = get_plugin("music_video")
        else:
            plugin = get_plugin("prompt_to_video")

    if not plugin:
        raise ValueError(f"No plugin found for job {job_id}")

    return job, plugin


async def _load_scenes(db: AsyncSession, job: Job) -> list[VideoScene]:
    """Load all scenes for a job, ordered by scene number."""
    result = await db.execute(
        select(VideoScene)
        .where(VideoScene.job_id == job.id)
        .order_by(VideoScene.scene_number)
    )
    return list(result.scalars().all())


async def dispatch_stage(job_id: str, stage: str) -> dict[str, Any]:
    """Run a single pipeline stage for a job via its plugin.

    Stages:
      - ``planning``       → plugin.enrich_inputs() + plugin.plan_scenes()
      - ``generating_images`` → plugin.generate_images()
      - ``generating_videos`` → plugin.generate_videos()
      - ``rendering``      → plugin.render()
    """
    async with ctx.session_factory() as db:
        job, plugin = await _load_job(db, job_id)
        context: dict[str, Any] = {}

        try:
            if stage == "planning":
                job.status = "processing"
                job.stage = "planning"
                await db.commit()

                # Enrich inputs (extract lyrics, parse scripts, etc.)
                context = await plugin.enrich_inputs(db, job, context)
                await db.commit()

                # Plan scenes
                result = await plugin.plan_scenes(db, job, context)
                job.stage = "planned"
                job.progress = 15
                await db.commit()
                return {"status": "completed", "job_id": job_id, "stage": "planned", **result}

            elif stage == "generating_images":
                job.stage = "generating_images"
                job.progress = 20
                await db.commit()

                scenes = await _load_scenes(db, job)
                context = await plugin.generate_images(db, job, scenes, context)

                # Reload scenes to check final status
                scenes = await _load_scenes(db, job)
                any_ready = any(s.status == "image_ready" for s in scenes)
                if any_ready:
                    job.stage = "images_ready"
                    job.progress = 40
                    await db.commit()
                    return {"status": "completed", "job_id": job_id, "stage": "images_ready"}
                else:
                    job.status = "failed"
                    job.stage = "generating_images"
                    job.error_message = "All image scenes failed to generate"
                    await db.commit()
                    return {"status": "failed", "job_id": job_id, "stage": "generating_images"}

            elif stage == "generating_videos":
                job.stage = "generating_videos"
                job.progress = 45
                await db.commit()

                scenes = await _load_scenes(db, job)
                context = await plugin.generate_videos(db, job, scenes, context)

                # Reload scenes to check final status
                scenes = await _load_scenes(db, job)
                any_ready = any(s.status == "video_ready" for s in scenes)
                if any_ready:
                    job.stage = "videos_ready"
                    job.progress = 80
                    await db.commit()
                    return {"status": "completed", "job_id": job_id, "stage": "videos_ready"}
                else:
                    job.status = "failed"
                    job.stage = "generating_videos"
                    job.error_message = "All video scenes failed to generate"
                    await db.commit()
                    return {"status": "failed", "job_id": job_id, "stage": "generating_videos"}

            elif stage == "rendering":
                job.stage = "rendering"
                await db.commit()

                scenes = await _load_scenes(db, job)
                render_result = await plugin.render(db, job, scenes, context)

                # Create MediaAssets for the final output
                final_asset = None
                try:
                    from app.services.auto_import import (
                        _create_asset_from_file,
                        _get_or_create_folder,
                    )

                    if render_result.get("output_path"):
                        from pathlib import Path

                        from app.config import get_settings
                        settings = get_settings()
                        storage = Path(settings.storage_path).resolve()
                        final_path = storage / render_result["output_path"]
                        if final_path.exists():
                            folder = await _get_or_create_folder(
                                user_id=job.user_id, name="Final Exports",
                                parent_id=None, db=db,
                            )
                            final_asset = await _create_asset_from_file(
                                user_id=job.user_id, folder_id=folder.id,
                                name=job.title,
                                file_path=final_path, file_type="video",
                                source_job_id=job.id, db=db,
                                project_id=job.project_id,
                            )
                except Exception:
                    logger.warning("Failed to create MediaAsset for final video", exc_info=True)

                job.status = "completed"
                job.stage = "completed"
                if render_result.get("output_path"):
                    job.output_path = render_result["output_path"]
                if render_result.get("preview_path"):
                    job.preview_path = render_result["preview_path"]
                from datetime import datetime
                job.completed_at = datetime.utcnow()
                await db.commit()

                if final_asset:
                    await record_and_publish_media_event(
                        db=db,
                        user_id=job.user_id,
                        event_type="created",
                        asset_id=final_asset.id,
                    )

                from app.workers.tasks import _post_completion_message

                await _post_completion_message(job.id, db=db)

                return {"status": "completed", "job_id": job_id, "stage": "completed", **render_result}

            else:
                raise ValueError(f"Unknown stage: {stage}")

        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            await db.commit()

            try:
                from app.services.error_capture import log_user_error
                from app.database import ErrorSeverity, ErrorOrigin
                friendly = str(exc)
                if len(friendly) > 200:
                    friendly = friendly[:200] + "..."
                await log_user_error(
                    db,
                    user_id=job.user_id,
                    severity=ErrorSeverity.ERROR,
                    origin=ErrorOrigin.VIDEO_GENERATION,
                    message=f"Job failed during {stage}: {friendly}",
                    details={"stage": stage, "error": str(exc), "job_id": str(job.id)},
                    source_id=job.id,
                    source_type="job",
                )
            except Exception:
                logger.warning("Failed to capture error for job %s", job_id, exc_info=True)

            raise


async def dispatch_scene_rerender(
    job_id: str,
    scene_id: str,
    media_type: str,
) -> dict[str, Any]:
    """Re-render a single scene's image or video via its plugin."""
    from uuid import UUID

    scene_uuid = UUID(scene_id)

    async with ctx.session_factory() as db:
        job, plugin = await _load_job(db, job_id)

        result = await db.execute(
            select(VideoScene).where(VideoScene.id == scene_uuid)
        )
        scene = result.scalar_one_or_none()
        if not scene:
            return {"status": "failed", "error": "Scene not found"}

        context: dict[str, Any] = {}

        try:
            if media_type == "image":
                path = await plugin.rerender_scene_image(db, job, scene, context)
            elif media_type == "video":
                path = await plugin.rerender_scene_video(db, job, scene, context)
            else:
                return {"status": "failed", "error": f"Unknown media type: {media_type}"}

            if path is None:
                return {"status": "failed", "error": "Re-render returned no path"}

            return {
                "status": "completed",
                "job_id": job_id,
                "scene_id": scene_id,
                "media_type": media_type,
                "path": path,
            }

        except Exception as exc:
            scene.status = "failed"
            scene.error_message = str(exc)
            await db.commit()

            try:
                from app.services.error_capture import log_user_error
                from app.database import ErrorSeverity, ErrorOrigin
                friendly = str(exc)
                if len(friendly) > 200:
                    friendly = friendly[:200] + "..."
                await log_user_error(
                    db,
                    user_id=job.user_id,
                    severity=ErrorSeverity.ERROR,
                    origin=ErrorOrigin.VIDEO_GENERATION,
                    message=f"Scene {media_type} generation failed: {friendly}",
                    details={"media_type": media_type, "error": str(exc), "job_id": str(job.id), "scene_id": str(scene.id)},
                    source_id=job.id,
                    source_type="job",
                )
            except Exception:
                logger.warning("Failed to capture error for scene re-render %s", job_id, exc_info=True)

            return {"status": "failed", "error": str(exc)}
