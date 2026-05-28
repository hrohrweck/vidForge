from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import ModelConfig

logger = logging.getLogger(__name__)


class ModelConfigService:
    """Single source of truth for all model configuration.

    Provides CRUD, query, and sync operations on the model_configs table.
    All methods accept an AsyncSession for clean dependency injection.
    """

    @staticmethod
    async def get_by_id(
        db: AsyncSession, model_id: str, provider_id: UUID
    ) -> ModelConfig | None:
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.model_id == model_id,
                ModelConfig.provider_id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_provider_model_id(
        db: AsyncSession, provider_model_id: str, provider_id: UUID
    ) -> ModelConfig | None:
        """Look up a ModelConfig by the provider's own model ID string."""
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.provider_model_id == provider_model_id,
                ModelConfig.provider_id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_provider(
        db: AsyncSession,
        provider_id: UUID,
        modality: str | None = None,
        active_only: bool = True,
    ) -> list[ModelConfig]:
        stmt = select(ModelConfig).where(ModelConfig.provider_id == provider_id)
        if active_only:
            stmt = stmt.where(ModelConfig.is_active == True)  # noqa: E712
        if modality:
            stmt = stmt.where(ModelConfig.modality == modality)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_modality(
        db: AsyncSession,
        modality: str,
        active_only: bool = True,
    ) -> list[ModelConfig]:
        stmt = select(ModelConfig).where(ModelConfig.modality == modality)
        if active_only:
            stmt = stmt.where(ModelConfig.is_active == True)  # noqa: E712
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ModelConfig:
        config = ModelConfig(**data)
        db.add(config)
        await db.flush()
        return config

    @staticmethod
    async def update(
        db: AsyncSession, model_id: str, provider_id: UUID, data: dict
    ) -> ModelConfig:
        config = await ModelConfigService.get_by_id(db, model_id, provider_id)
        if config is None:
            raise ValueError(
                f"ModelConfig not found: model_id={model_id}, provider_id={provider_id}"
            )
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        await db.flush()
        return config

    @staticmethod
    async def delete(
        db: AsyncSession, model_id: str, provider_id: UUID
    ) -> None:
        config = await ModelConfigService.get_by_id(db, model_id, provider_id)
        if config is not None:
            config.is_active = False
            await db.flush()

    @staticmethod
    async def get_or_create(
        db: AsyncSession,
        provider_id: UUID,
        model_id: str,
        defaults: dict,
    ) -> ModelConfig:
        config = await ModelConfigService.get_by_id(db, model_id, provider_id)
        if config:
            if config.is_deprecated:
                logger.warning(
                    "Using deprecated model config: model_id=%s provider_id=%s",
                    model_id, provider_id,
                )
            return config

        create_data = {
            "provider_id": provider_id,
            "model_id": model_id,
            "display_name": defaults.get("display_name", model_id),
            "provider_model_id": defaults.get("provider_model_id", model_id),
            "modality": defaults.get("modality", "image"),
            "endpoint_type": defaults.get("endpoint_type", "comfyui"),
        }
        for key in (
            "prompt_format", "parameter_map", "extra_params",
            "capabilities", "constraints", "cost_config",
            "comfyui_workflow",
        ):
            if key in defaults:
                create_data[key] = defaults[key]

        return await ModelConfigService.create(db, create_data)

    @staticmethod
    async def mark_deprecated(
        db: AsyncSession, model_id: str, provider_id: UUID
    ) -> None:
        config = await ModelConfigService.get_by_id(db, model_id, provider_id)
        if config is None:
            raise ValueError(
                f"ModelConfig not found: model_id={model_id}, provider_id={provider_id}"
            )
        config.is_deprecated = True
        config.is_active = False
        await db.flush()
        logger.info(
            "Model config deprecated: model_id=%s provider_id=%s",
            model_id, provider_id,
        )

    @staticmethod
    async def set_last_synced(
        db: AsyncSession, model_id: str, provider_id: UUID
    ) -> None:
        from datetime import datetime

        config = await ModelConfigService.get_by_id(db, model_id, provider_id)
        if config is not None:
            config.last_synced_at = datetime.utcnow()
            await db.flush()
