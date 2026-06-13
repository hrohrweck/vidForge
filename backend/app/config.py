import secrets
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "VidForge"
    app_version: str = "0.1.0"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://vidforge:vidforge@localhost:5432/vidforge"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    comfyui_url: str = "http://localhost:8188"
    comfyui_workflows_path: str = "./app/comfyui/workflows"
    comfyui_max_concurrent: int = 1
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3.6:35b"
    llm_timeout_seconds: float = 3600.0
    chat_max_iterations: int = 16
    audiocraft_url: str = "http://localhost:5050"

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
    ssh_known_hosts_path: str = "~/.ssh/known_hosts"

    preview_width: int = 854
    preview_height: int = 480
    preview_fps: int = 15
    preview_quality: int = 28

    task_time_limit: int = 172800

    worker_id: str = "local-worker-1"
    worker_name: str = "Local GPU Worker"
    worker_heartbeat_interval: int = 30

    ws_heartbeat_interval_seconds: float = 20.0
    ws_heartbeat_timeout_seconds: float = 60.0

    default_provider_preference: Literal["comfyui_direct", "runpod", "auto"] = "auto"

    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""
    runpod_cost_per_gpu_hour: Decimal = Decimal("0.69")
    runpod_idle_timeout: int = 30
    runpod_flashboot_enabled: bool = True
    runpod_max_workers: int = 3

    admin_email: str = "admin@vidforge.dev"
    admin_password: str | None = None

    @field_validator("secret_key")
    @classmethod
    def reject_weak_secret_key(cls, v: str) -> str:
        if not v or v == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY is unset or uses the default value. "
                "Set a strong random secret via the SECRET_KEY environment variable."
            )
        return v

    @model_validator(mode="after")
    def randomize_admin_password(self) -> "Settings":
        if self.admin_password is None:
            self.admin_password = secrets.token_urlsafe(16)
            print("[Config] ADMIN_PASSWORD not set. Generated random admin password.")
        return self

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
