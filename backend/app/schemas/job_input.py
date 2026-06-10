from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class JobInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
