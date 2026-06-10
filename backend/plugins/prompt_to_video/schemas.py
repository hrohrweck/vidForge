from __future__ import annotations

from pydantic import field_validator

from app.schemas.job_input import JobInputSchema
from app.schemas.job_input_common import AvatarAssignment, ModelPreferences


class PromptToVideoInput(JobInputSchema):
    prompt: str
    style: str = "realistic"
    duration: int = 30
    aspect_ratio: str = "16:9"
    fps: int = 24
    generate_audio: bool = False
    enhance_prompt: bool = True
    avatars: list[AvatarAssignment] | None = None
    models: ModelPreferences | None = None

    @field_validator("style")
    @classmethod
    def _valid_style(cls, v: str) -> str:
        allowed = {"realistic", "anime", "manga"}
        if v not in allowed:
            raise ValueError(f"style must be one of {allowed}")
        return v

    @field_validator("aspect_ratio")
    @classmethod
    def _valid_aspect_ratio(cls, v: str) -> str:
        allowed = {"16:9", "9:16", "1:1"}
        if v not in allowed:
            raise ValueError(f"aspect_ratio must be one of {allowed}")
        return v

    @field_validator("duration")
    @classmethod
    def _valid_duration(cls, v: int) -> int:
        if not (2 <= v <= 600):
            raise ValueError("duration must be between 2 and 600")
        return v

    @field_validator("fps")
    @classmethod
    def _valid_fps(cls, v: int) -> int:
        if not (15 <= v <= 60):
            raise ValueError("fps must be between 15 and 60")
        return v
