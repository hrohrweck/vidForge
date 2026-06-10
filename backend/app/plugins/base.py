"""
Base class that every template plugin must implement.

The core scene lifecycle is:

    pending → planning → planned → generating_images → images_ready
    → generating_videos → videos_ready → rendering → completed

At each transition the core calls the corresponding method on the
plugin that owns the job's template. Plugins can override any stage;
sensible defaults are provided for the common case (generate per-scene
images then per-scene videos then merge).
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from app.plugins.enrichment import EnrichmentMixin
from app.plugins.media_stages import MediaStagesMixin
from app.services.error_mapping import classify_provider_error

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pydantic import BaseModel
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import Job


class PluginBase(EnrichmentMixin, MediaStagesMixin, ABC):
    """Contract every template plugin must implement."""

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier, e.g. ``'music_video'``."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description."""

    # ------------------------------------------------------------------
    # Template definition
    # ------------------------------------------------------------------

    @abstractmethod
    def get_template_definition(self) -> dict[str, Any]:
        """Return the template definition (inputs, pipeline, stages …).

        The dict has the same shape as a ``templates/*.yaml`` file.
        """

    async def plan_scenes(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyse inputs and create :class:`VideoScene` rows.

        Must create :class:`VideoScene` objects in the DB.
        Returns a context dict forwarded to subsequent stages.

        Example return::

            {"scene_count": 12, "summary": "..."}
        """
        raise NotImplementedError

    def _is_recoverable(self, exc: Exception) -> bool:
        """Return True if *exc* looks like a transient error worth retrying."""
        return classify_provider_error(exc).recoverable

    async def _retry(
        self,
        fn,
        *args,
        max_retries: int = 4,
        base_delay: float = 10.0,
        label: str = "operation",
        **kwargs,
    ):
        """Call ``await fn(*args, **kwargs)`` with exponential backoff.

        Retries up to *max_retries* times on recoverable errors.
        Non-recoverable errors propagate immediately.
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if not self._is_recoverable(exc):
                    raise
                if attempt >= max_retries:
                    raise
                delay = base_delay * (2 ** attempt)  # 10s, 20s, 40s, 80s
                logger.warning(
                    "[%s] Attempt %d/%d failed (recoverable): %s — "
                    "retrying in %.0fs",
                    label, attempt + 1, max_retries + 1, exc, delay,
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def get_ui_schema(self) -> dict[str, Any]:
        """Return a JSON schema describing the template's editor UI.

        The default auto-generates from the template definition's inputs.
        """
        return {}

    def get_editor_panels(self) -> list[dict[str, Any]]:
        """Return editor panels for the scene editor.

        Default panels: scenes grid, timeline, export.
        """
        return [
            {"id": "scenes", "label": "Scenes", "component": "SceneGrid"},
            {"id": "timeline", "label": "Timeline", "component": "Timeline"},
            {"id": "export", "label": "Export", "component": "ExportPanel"},
        ]

    def get_export_options_schema(self) -> dict[str, Any]:
        """Return a JSON schema for template-specific export options."""
        return {}

    def get_input_schema(self) -> type[BaseModel] | None:
        return None


async def _import_scene_asset(
    db, job, file_path, name, file_type, scene_number,
) -> None:
    """Import a generated scene asset into the media library."""
    if not file_path:
        return
    try:
        from pathlib import Path

        from app.config import get_settings
        from app.services.auto_import import (
            _create_asset_from_file,
            _get_or_create_folder,
        )

        settings = get_settings()
        storage = Path(settings.storage_path).resolve()
        full_path = storage / file_path
        if not full_path.exists():
            return

        # Create/use a per-job folder under /Generated
        gen_folder = await _get_or_create_folder(
            user_id=job.user_id,
            name="Generated",
            parent_id=None,
            db=db,
        )
        job_folder = await _get_or_create_folder(
            user_id=job.user_id,
            name=job.title or f"Job-{str(job.id)[:8]}",
            parent_id=gen_folder.id,
            db=db,
        )

        await _create_asset_from_file(
            user_id=job.user_id,
            folder_id=job_folder.id,
            file_path=full_path,
            name=name,
            file_type=file_type,
            source_job_id=job.id,
            db=db,
        )
    except Exception:
        pass  # Non-critical — don't fail the pipeline if import fails
