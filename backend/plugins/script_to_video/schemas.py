from __future__ import annotations

from pydantic import field_validator

from app.schemas.job_input import JobInputSchema
from app.schemas.job_input_common import AvatarAssignment, ModelPreferences


class ScriptToVideoInput(JobInputSchema):
    script: str
    style: str = "realistic"
    voice: str = "default"
    aspect_ratio: str = "16:9"
    background_music: bool = True
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

    @field_validator("voice")
    @classmethod
    def _valid_voice(cls, v: str) -> str:
        allowed = {"default", "male", "female", "deep", "none"}
        if v not in allowed:
            raise ValueError(f"voice must be one of {allowed}")
        return v
