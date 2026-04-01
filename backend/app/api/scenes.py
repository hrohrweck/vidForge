from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import Job, User, VideoScene, get_db
from app.services.lyrics_extractor import LyricsExtractor
from app.services.music_video_planner import MusicVideoPlanner

router = APIRouter(tags=["scenes"])


class LyricsExtractRequest(BaseModel):
    audio_file_path: str


class ManualLyricsRequest(BaseModel):
    lyrics_text: str
    duration: float


class ScenePlanRequest(BaseModel):
    lyrics_data: dict[str, Any]
    duration: float
    style: str = "realistic"


class SceneUpdate(BaseModel):
    start_time: float | None = None
    end_time: float | None = None
    lyrics_segment: str | None = None
    visual_description: str | None = None
    image_prompt: str | None = None
    mood: str | None = None
    camera_movement: str | None = None
    reference_image_path: str | None = None


class SceneResponse(BaseModel):
    id: UUID
    job_id: UUID
    scene_number: int
    start_time: float
    end_time: float
    lyrics_segment: str | None
    visual_description: str | None
    image_prompt: str | None
    mood: str
    camera_movement: str
    reference_image_path: str | None
    thumbnail_path: str | None
    generated_video_path: str | None
    status: str
    created_at: Any

    class Config:
        from_attributes = True


class JobStageUpdate(BaseModel):
    stage: str = Field(..., pattern="^(planning|generating|rendering|completed)$")


@router.post("/{job_id}/lyrics/extract")
async def extract_lyrics(
    job_id: UUID,
    request: LyricsExtractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    extractor = LyricsExtractor()
    try:
        lyrics = await extractor.extract_from_audio(request.audio_file_path)
    finally:
        await extractor.close()

    job.input_data = job.input_data or {}
    job.input_data["lyrics"] = lyrics
    await db.commit()

    return {"lyrics": lyrics}


@router.post("/{job_id}/lyrics/manual")
async def set_manual_lyrics(
    job_id: UUID,
    request: ManualLyricsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lyrics = LyricsExtractor.parse_manual_lyrics(request.lyrics_text, request.duration)

    job.input_data = job.input_data or {}
    job.input_data["lyrics"] = lyrics
    await db.commit()

    return {"lyrics": lyrics}


@router.post("/{job_id}/scenes/plan")
async def plan_scenes(
    job_id: UUID,
    request: ScenePlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    planner = MusicVideoPlanner()
    try:
        plan = await planner.plan_music_video(
            lyrics=request.lyrics_data, duration=request.duration, style=request.style
        )
    finally:
        await planner.close()

    await db.execute(
        select(VideoScene).where(VideoScene.job_id == job_id).delete()
    )
    await db.commit()

    scenes = []
    for scene_data in plan.get("scenes", []):
        scene = VideoScene(
            job_id=job_id,
            scene_number=scene_data["scene_number"],
            start_time=scene_data["start_time"],
            end_time=scene_data["end_time"],
            lyrics_segment=scene_data.get("lyrics_segment"),
            visual_description=scene_data.get("visual_description"),
            image_prompt=scene_data.get("image_prompt"),
            mood=scene_data.get("mood", "neutral"),
            camera_movement=scene_data.get("camera_movement", "static"),
            status="pending",
        )
        db.add(scene)
        scenes.append(scene)

    job.stage = "planning"
    await db.commit()
    for scene in scenes:
        await db.refresh(scene)

    return {"scenes": plan.get("scenes", []), "summary": plan.get("summary", "")}


@router.get("/{job_id}/scenes")
async def get_scenes(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SceneResponse]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(VideoScene).where(VideoScene.job_id == job_id).order_by(VideoScene.scene_number)
    )
    scenes = result.scalars().all()

    return list(scenes)


@router.patch("/{job_id}/scenes/{scene_id}")
async def update_scene(
    job_id: UUID,
    scene_id: UUID,
    updates: SceneUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SceneResponse:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(VideoScene).where(VideoScene.id == scene_id, VideoScene.job_id == job_id)
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    if updates.start_time is not None:
        scene.start_time = updates.start_time
    if updates.end_time is not None:
        scene.end_time = updates.end_time
    if updates.lyrics_segment is not None:
        scene.lyrics_segment = updates.lyrics_segment
    if updates.visual_description is not None:
        scene.visual_description = updates.visual_description
    if updates.image_prompt is not None:
        scene.image_prompt = updates.image_prompt
    if updates.mood is not None:
        scene.mood = updates.mood
    if updates.camera_movement is not None:
        scene.camera_movement = updates.camera_movement
    if updates.reference_image_path is not None:
        scene.reference_image_path = updates.reference_image_path

    await db.commit()
    await db.refresh(scene)

    return scene


@router.delete("/{job_id}/scenes/{scene_id}")
async def delete_scene(
    job_id: UUID,
    scene_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(VideoScene).where(VideoScene.id == scene_id, VideoScene.job_id == job_id)
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    await db.delete(scene)
    await db.commit()

    return {"status": "deleted"}


@router.post("/{job_id}/scenes/reorder")
async def reorder_scenes(
    job_id: UUID,
    scene_ids: list[UUID],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for i, scene_id in enumerate(scene_ids):
        result = await db.execute(
            select(VideoScene).where(VideoScene.id == scene_id, VideoScene.job_id == job_id)
        )
        scene = result.scalar_one_or_none()
        if scene:
            scene.scene_number = i + 1
            await db.refresh(scene)

    await db.commit()

    return {"status": "reordered"}


@router.patch("/{job_id}/stage")
async def update_job_stage(
    job_id: UUID,
    updates: JobStageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.stage = updates.stage
    await db.commit()

    return {"job_id": str(job_id), "stage": updates.stage}


@router.post("/{job_id}/scenes/regenerate-prompts")
async def regenerate_scene_prompts(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(VideoScene).where(VideoScene.job_id == job_id).order_by(VideoScene.scene_number)
    )
    scenes = result.scalars().all()

    if not scenes:
        raise HTTPException(status_code=400, detail="No scenes to regenerate")

    lyrics = job.input_data.get("lyrics", {}) if job.input_data else {}
    lyrics_context = lyrics.get("full_text", "")

    planner = MusicVideoPlanner()
    updated_scenes = []

    try:
        for scene in scenes:
            scene_dict = {
                "scene_number": scene.scene_number,
                "start_time": scene.start_time,
                "end_time": scene.end_time,
                "lyrics_segment": scene.lyrics_segment,
                "visual_description": scene.visual_description,
                "mood": scene.mood,
                "camera_movement": scene.camera_movement,
            }

            updated = await planner.regenerate_scene_prompt(
                scene=scene_dict,
                lyrics_context=lyrics_context,
                style=job.input_data.get("style", "realistic") if job.input_data else "realistic",
            )

            scene.image_prompt = updated.get("image_prompt", scene.image_prompt)
            scene.visual_description = updated.get("visual_description", scene.visual_description)
            scene.mood = updated.get("mood", scene.mood)

            updated_scenes.append(scene)
    finally:
        await planner.close()

    await db.commit()

    return {"scenes": [{"id": str(s.id), "image_prompt": s.image_prompt} for s in updated_scenes]}
