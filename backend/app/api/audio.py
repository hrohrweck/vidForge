"""Audio generation endpoints — background music via AudioCraft/MusicGen."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user, get_current_user_from_bearer_or_cookie
from app.config import get_settings
from app.database import User
from app.services.audio_generation import MusicGenService

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────


class MusicGenRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    duration: float = Field(15.0, ge=1.0, le=120.0)
    output_format: str = Field("mp3", pattern="^(wav|mp3)$")


class MusicGenResponse(BaseModel):
    path: str
    filename: str
    duration: float


class AudioCraftStatus(BaseModel):
    available: bool
    url: str


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/status", response_model=AudioCraftStatus)
async def get_audiocraft_status(
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
) -> AudioCraftStatus:
    settings = get_settings()
    svc = MusicGenService()
    return AudioCraftStatus(
        available=await svc.is_available(),
        url=settings.audiocraft_url,
    )


@router.post("/generate-music", response_model=MusicGenResponse)
async def generate_music(
    req: MusicGenRequest,
    current_user: User = Depends(get_current_user_from_bearer_or_cookie),
) -> MusicGenResponse:
    svc = MusicGenService()
    if not await svc.is_available():
        raise HTTPException(503, "AudioCraft server is not available")

    settings = get_settings()
    output_dir = Path(settings.storage_path) / "music"
    output_dir.mkdir(parents=True, exist_ok=True)

    import uuid

    ext = req.output_format
    output_path = str(output_dir / f"bgm_{uuid.uuid4().hex[:8]}.{ext}")

    try:
        path = await svc.generate(
            prompt=req.prompt,
            output_path=output_path,
            duration=req.duration,
            output_format=req.output_format,
        )
    except Exception as exc:
        raise HTTPException(500, f"Music generation failed: {exc}") from exc

    p = Path(path)
    return MusicGenResponse(
        path=str(p.relative_to(Path(settings.storage_path).resolve()))
        if p.is_relative_to(Path(settings.storage_path).resolve())
        else str(p),
        filename=p.name,
        duration=req.duration,
    )
