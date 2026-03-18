from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "VidForge"
    app_version: str = "0.1.0"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://vidforge:vidforge@localhost:5432/vidforge"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    comfyui_url: str = "http://localhost:8188"
    comfyui_workflows_path: str = "./app/comfyui/workflows"
    ollama_url: str = "http://localhost:11434"

    templates_path: str = "./templates"
    styles_path: str = "./styles"

    storage_backend: Literal["local", "s3", "ssh"] = "local"
    storage_path: str = "./storage"

    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"

    ssh_host: str = ""
    ssh_user: str = ""
    ssh_key_path: str = ""
    ssh_remote_path: str = "/var/lib/vidforge/storage"

    preview_width: int = 854
    preview_height: int = 480
    preview_fps: int = 15
    preview_quality: int = 28


@lru_cache
def get_settings() -> Settings:
    return Settings()
