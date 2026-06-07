"""
Base class that every template plugin must implement.

The core scene lifecycle is:

    pending → planning → planned → generating_images → images_ready
    → generating_videos → videos_ready → rendering → completed

At each transition the core calls the corresponding method on the
plugin that owns the job's template.  Plugins can override any stage;
sensible defaults are provided for the common case (generate per-scene
images then per-scene videos then merge).
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import Job, VideoScene


class PluginBase(ABC):
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

    # ------------------------------------------------------------------
    # Stage: enrich inputs (optional)
    # ------------------------------------------------------------------

    async def enrich_inputs(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Pre-process raw inputs before scene planning.

        E.g. extract lyrics from audio, parse script annotations.
        Update ``job.input_data`` with enriched fields.
        Return an updated *context* dict that is forwarded to
        :meth:`plan_scenes`.

        Also resolves avatar assignments from ``job.input_data["avatars"]``
        into ``context["avatars"]`` as a list of resolved avatar dicts.
        """
        context = await self._resolve_avatars(db, job, context)
        if not context.get("avatars"):
            context = await self._create_auto_avatars(db, job, context)
        return context

    async def _resolve_avatars(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve avatar assignments from job.input_data into the context dict.

        Reads ``job.input_data["avatars"]`` (list of {avatar_id, role, ...}),
        looks up full Avatar+AvatarImage data from the database, resolves
        file-system paths for images, and populates ``context["avatars"]``.

        Missing or soft-deleted avatars are logged as warnings and skipped.
        Avatars with no valid primary image are skipped.
        """
        from pathlib import Path
        from uuid import UUID

        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.config import get_settings
        from app.database import Avatar

        input_data = job.input_data or {}
        avatar_assignments = input_data.get("avatars", [])

        if not avatar_assignments:
            return context

        settings = get_settings()
        storage_root = Path(settings.storage_path)
        resolved: list[dict[str, Any]] = []

        for assignment in avatar_assignments:
            avatar_id = assignment.get("avatar_id")
            if not avatar_id:
                continue

            # Normalise to UUID
            if isinstance(avatar_id, str):
                try:
                    avatar_id = UUID(avatar_id)
                except ValueError:
                    logger.warning("Invalid avatar_id %r, skipping", avatar_id)
                    continue

            result = await db.execute(
                select(Avatar)
                .options(selectinload(Avatar.images))
                .where(Avatar.id == avatar_id),
            )
            avatar = result.scalar_one_or_none()

            if not avatar:
                logger.warning("Avatar %s not found, skipping", avatar_id)
                continue

            if avatar.deleted_at:
                logger.warning(
                    "Avatar %s (%r) is soft-deleted, including with warning",
                    avatar.id,
                    avatar.name,
                )

            # --- Resolve primary image ---
            primary = avatar.primary_image
            if not primary:
                # Fallback: first image marked primary, or first image
                primary = next(
                    (img for img in avatar.images if img.is_primary), None
                )
                if not primary and avatar.images:
                    primary = avatar.images[0]

            if not primary:
                logger.error(
                    "Avatar %s has no images, skipping", avatar.id
                )
                continue

            primary_path = (
                str(storage_root / primary.storage_path)
                if primary.storage_path
                else None
            )

            if primary_path and not Path(primary_path).exists():
                logger.error(
                    "Avatar %s primary image missing from disk: %s, skipping",
                    avatar.id,
                    primary_path,
                )
                continue

            # Compose resolved avatar dict
            resolved.append({
                "id": str(avatar.id),
                "name": avatar.name,
                "gender": avatar.gender,
                "bio": avatar.bio,
                "role": assignment.get("role"),
                "consistency_strategy": (
                    assignment.get("consistency_strategy_override")
                    or avatar.consistency_strategy
                ),
                "primary_image_path": primary_path,
                "all_image_paths": [
                    str(storage_root / img.storage_path)
                    for img in avatar.images
                    if img.storage_path
                ],
                "deleted": bool(avatar.deleted_at),
            })

        context["avatars"] = resolved
        return context

    async def _create_auto_avatars(
        self,
        db: AsyncSession,
        job: Job,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Auto-create characters when no avatars are selected for a job.

        1. Use LLM to analyze the job prompt and create 1-3 character descriptions.
        2. Generate reference images for each character.
        3. Persist Avatar + AvatarImage records to the database.
        4. Populate ``context["avatars"]`` with resolved dicts.

        If any step fails gracefully (LLM unavailable, image generation fails,
        invalid response), the method returns *context* unchanged.
        """
        import json as _json
        from pathlib import Path

        from app.api.models import get_default_model_preferences
        from app.config import get_settings
        from app.database import Avatar, AvatarImage, JobObjectRef, ObjectRef
        from app.services.llm_service import LLMClient
        from app.services.media_generator import generate_image

        # ── Locate the job prompt ──────────────────────────────────────
        input_data = job.input_data or {}
        prompt = input_data.get("enhanced_prompt") or input_data.get("prompt", "")
        if not prompt or not prompt.strip():
            logger.debug("No prompt in job %s, skipping auto-avatar creation", job.id)
            context.setdefault("objects", [])
            return context

        # ── LLM: create character + object descriptions ─────────────────
        system = (
            "You are a scene analyst. Based on the video prompt, identify:\n"
            "1. CHARACTERS (1-3): people with name, gender (male/female/other), bio, role\n"
            "2. OBJECTS (0-5): recurring props/items/vehicles/tools that appear in multiple "
            "scenes.\n"
            "   For each object: name, description (1-2 sentences), visual_properties (dict of "
            "   color, make, model, size, distinctive features), role (how the object appears "
            "   in the story)\n\n"
            "Output ONLY valid JSON:\n"
            '{"characters": [{"name": "...", "gender": "...", "bio": "...", "role": "..."}],\n'
            ' "objects": [{"name": "...", "description": "...", "visual_properties": {...}, '
            '"role": "..."}]}\n\n'
            "Only include objects that are RECURRING and STORY-SIGNIFICANT. Skip one-off "
            "mentions. A car that appears in 3+ scenes is important. A wristwatch mentioned "
            "once is not.\n"
            "Max 5 objects. Be precise about visual properties — they must remain consistent "
            "across scenes."
        )

        try:
            llm = LLMClient()
            response = await llm.generate(
                prompt=f"Video prompt: {prompt}",
                system=system,
                max_tokens=1024,
                temperature=0.8,
            )
        except Exception as exc:
            logger.warning(
                "LLM unavailable during auto-avatar creation for job %s: %s",
                job.id, exc,
            )
            context.setdefault("objects", [])
            return context

        # ── Parse JSON ─────────────────────────────────────────────────
        try:
            text = response.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)
            data = _json.loads(text)
            characters: list[dict[str, Any]] = data.get("characters", [])
            objects_data: list[dict[str, Any]] = data.get("objects", [])
        except (_json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "Failed to parse auto-avatar LLM response for job %s: %s\nResponse: %s",
                job.id, exc, response[:500],
            )
            context.setdefault("objects", [])
            return context

        if not characters:
            logger.debug("LLM returned empty character list for job %s", job.id)

        if not characters and not objects_data:
            context.setdefault("objects", [])
            return context

        # ── Generate images & persist ──────────────────────────────────
        settings = get_settings()
        storage_root = Path(settings.storage_path)
        defaults = await get_default_model_preferences(db)
        image_model = defaults.get("text_to_image_model") or defaults.get("image_model", "")
        resolved_avatars: list[dict[str, Any]] = []

        for char in characters:
            name = char.get("name", "Unnamed")
            gender = char.get("gender", "other")
            bio = char.get("bio", "")
            role = char.get("role", "")

            # Generate reference portrait
            image_path: str | None = None
            try:
                img_prompt = (
                    f"Portrait of {name}, {gender}, {bio}. "
                    "Clean background, well-lit, photorealistic portrait, looking at camera."
                )
                relative_path, _model_id, _pid = await generate_image(
                    db=db,
                    job=job,
                    prompt=img_prompt,
                    scene_number=0,  # special: auto-avatar generation
                    model_preference=image_model if image_model else None,
                    aspect_ratio="1:1",
                    title=f"avatar_{name}",
                )
                # Verify the file actually exists on disk
                full_path = storage_root / relative_path
                if not full_path.exists():
                    logger.error(
                        "Generated avatar image not found on disk for %s: %s",
                        name, full_path,
                    )
                    image_path = None
                else:
                    image_path = relative_path
            except Exception as exc:
                logger.warning(
                    "Image generation failed for auto-avatar %r (job %s): %s — "
                    "character will be text-only (no reference image)",
                    name, job.id, exc,
                )

            # Persist avatar record
            try:
                avatar = Avatar(
                    name=name,
                    gender=gender,
                    bio=bio,
                    user_id=job.user_id,
                    consistency_strategy="prompt_only",
                )
                db.add(avatar)
                await db.flush()  # get avatar.id

                if image_path:
                    avatar_img = AvatarImage(
                        avatar_id=avatar.id,
                        storage_path=image_path,
                        is_primary=True,
                        sort_order=0,
                    )
                    db.add(avatar_img)
                    await db.flush()
                    avatar.primary_image_id = avatar_img.id

                await db.commit()
                await db.refresh(avatar)
            except Exception as exc:
                logger.error(
                    "Failed to persist auto-avatar %r for job %s: %s",
                    name, job.id, exc,
                )
                await db.rollback()
                continue

            # Build resolved dict matching _resolve_avatars format
            resolved_avatars.append({
                "id": str(avatar.id),
                "name": avatar.name,
                "gender": avatar.gender,
                "bio": avatar.bio,
                "role": role,
                "consistency_strategy": avatar.consistency_strategy,
                "primary_image_path": str(storage_root / image_path) if image_path else None,
                "all_image_paths": [str(storage_root / image_path)] if image_path else [],
                "deleted": False,
            })

        context["avatars"] = resolved_avatars

        # ── Persist objects (no images yet — deferred to Task 8) ───────
        resolved_objects: list[dict[str, Any]] = []
        for idx, obj_data in enumerate(objects_data[:5]):
            obj_name = obj_data.get("name") or f"Object {idx + 1}"
            description = obj_data.get("description", "")
            visual_props = obj_data.get("visual_properties") or {}
            obj_role = obj_data.get("role", "")

            try:
                obj = ObjectRef(
                    user_id=job.user_id,
                    name=obj_name,
                    description=description if description else None,
                    visual_properties=visual_props if visual_props else None,
                    category=obj_data.get("category"),
                )
                db.add(obj)
                await db.flush()

                job_obj = JobObjectRef(
                    job_id=job.id,
                    object_ref_id=obj.id,
                    role=obj_role if obj_role else None,
                    importance_score=None,
                )
                db.add(job_obj)
                await db.commit()
                await db.refresh(obj)
            except Exception as exc:
                logger.error(
                    "Failed to persist auto-object %r for job %s: %s",
                    obj_name, job.id, exc,
                )
                await db.rollback()
                continue

            resolved_objects.append({
                "id": str(obj.id),
                "name": obj.name,
                "description": obj.description,
                "visual_properties": obj.visual_properties,
                "role": obj_role,
                "primary_image_path": None,
            })

        if resolved_objects:
            logger.info(
                "Auto-created %d object(s) from prompt for job %s: %s",
                len(resolved_objects), job.id,
                [o["name"] for o in resolved_objects],
            )

        context["objects"] = resolved_objects
        return context

    # ------------------------------------------------------------------
    # Stage: plan scenes
    # ------------------------------------------------------------------

    @abstractmethod
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

    # ------------------------------------------------------------------
    # Stage: generate images
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    # Error substrings that indicate a transient / recoverable problem.
    _RECOVERABLE_MARKERS: tuple[str, ...] = (
        "overloaded",
        "rate limit",
        "rate_limit",
        "too many requests",
        "429",
        "503",
        "502",
        "timeout",
        "timed out",
        "connection",
        "connectionerror",
        "connection refused",
        "temporary",
        "retry",
        "capacity",
        "queue is full",
        "server error",
        "internal server error",
        "no output data",
        "returned no data",
        "returned no image",
        "returned no video",
    )

    @staticmethod
    def _is_recoverable(exc: Exception) -> bool:
        """Return True if *exc* looks like a transient error worth retrying."""
        msg = str(exc).lower()
        return any(marker in msg for marker in PluginBase._RECOVERABLE_MARKERS)

    @staticmethod
    async def _retry(
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
                if not PluginBase._is_recoverable(exc):
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

    # ------------------------------------------------------------------
    # Deferred object reference image generation
    # ------------------------------------------------------------------

    async def _generate_object_references(
        self,
        db: "AsyncSession",
        job: "Job",
        context: dict[str, Any],
    ) -> None:
        """Generate reference images for objects the planner selected.

        Called from :meth:`generate_images` before the scene loop.  Only
        objects listed in ``context["object_selections"]`` get a reference
        image.  Objects that are not selected, or whose generation fails,
        stay text-only.
        """
        from pathlib import Path
        from uuid import UUID

        from sqlalchemy import select

        from app.config import get_settings
        from app.database import ObjectRef, ObjectRefImage
        from app.services.media_generator import generate_image

        object_selections: list[dict[str, Any]] = context.get("object_selections", [])
        if not object_selections:
            return

        objects: list[dict[str, Any]] = context.get("objects", [])
        if not objects:
            return

        for selection in object_selections:
            obj_name: str | None = selection.get("object_name")
            seed_prompt: str = selection.get("seed_image_prompt", "")
            if not obj_name or not seed_prompt:
                continue

            # Find the matching object in the resolved context list
            obj: dict[str, Any] | None = next(
                (o for o in objects if o.get("name") == obj_name), None
            )
            if not obj:
                logger.warning(
                    "Object %r selected by planner but not found in context.objects",
                    obj_name,
                )
                continue

            try:
                image_path, _media_id, _provider_id = await self._retry(
                    generate_image,
                    db=db,
                    job=job,
                    prompt=seed_prompt,
                    scene_number=0,  # object reference — not scene-specific
                    model_preference=job.input_data.get("image_model") if job.input_data else None,
                    provider_id=job.image_provider_id,
                    label=f"obj-ref-{obj_name}",
                )

                # Persist ObjectRefImage record
                result = await db.execute(
                    select(ObjectRef).where(ObjectRef.id == UUID(obj["id"]))
                )
                obj_ref = result.scalar_one_or_none()
                if obj_ref:
                    obj_img = ObjectRefImage(
                        object_ref_id=obj_ref.id,
                        storage_path=image_path,
                        is_primary=True,
                    )
                    db.add(obj_img)
                    await db.commit()

                    settings = get_settings()
                    obj["primary_image_path"] = str(Path(settings.storage_path) / image_path)
                    logger.info(
                        "Generated object reference for %r (path=%s)",
                        obj_name, image_path,
                    )
                else:
                    logger.warning(
                        "ObjectRef row not found for context object %r (id=%s)",
                        obj_name, obj["id"],
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to generate object reference for %r: %s — "
                    "object will be text-only",
                    obj_name, exc,
                )

        context["objects"] = objects

    # ------------------------------------------------------------------
    # Stage: generate images
    # ------------------------------------------------------------------

    async def generate_images(
        self,
        db: AsyncSession,
        job: Job,
        scenes: list[VideoScene],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate seed / reference images for each scene.

        The default implementation iterates over *scenes* and calls the
        core image generator for each scene's ``image_prompt``.
        """
        from pathlib import Path

        from app.services.media_generator import generate_image

        input_data = job.input_data or {}
        image_model = input_data.get("image_model")

        # Extract avatar reference images from context
        avatars = context.get("avatars", [])
        avatar_ref_path: str | None = None
        if avatars:
            first = avatars[0]
            avatar_ref_path = first.get("primary_image_path")
            if not avatar_ref_path:
                logger.warning(
                    "Avatar %s has no primary_image_path, "
                    "falling back to text-to-image",
                    first.get("name", first.get("id", "unknown")),
                )
                avatar_ref_path = None
            elif not Path(avatar_ref_path).exists():
                logger.warning(
                    "Avatar %s primary image not found on disk at %s, "
                    "falling back to text-to-image",
                    first.get("name", first.get("id", "unknown")),
                    avatar_ref_path,
                )
                avatar_ref_path = None

        await self._generate_object_references(db, job, context)

        for scene in scenes:
            if scene.reference_image_path:
                continue
            prompt = scene.image_prompt or scene.visual_description or ""
            if not prompt:
                continue

            # Inject object visual properties for this scene
            objects_ctx = context.get("objects", [])
            object_selections_ctx = context.get("object_selections", [])
            if objects_ctx and object_selections_ctx:
                scene_objects = [
                    sel for sel in object_selections_ctx
                    if scene.scene_number in sel.get("scenes", [])
                ]
                if scene_objects:
                    best = max(scene_objects, key=lambda s: s.get("importance_score", 0))
                    obj = next(
                        (o for o in objects_ctx if o.get("name") == best.get("object_name")),
                        None,
                    )
                    if obj and obj.get("primary_image_path"):
                        obj_visual = obj.get("visual_properties", {})
                        if obj_visual:
                            props_str = ", ".join(
                                f"{k}={v}" for k, v in obj_visual.items()
                            )
                            prompt = f"{prompt} [Object reference: {props_str}]"

            try:
                image_path, _media_id, _provider_id = await self._retry(
                    generate_image,
                    db=db,
                    job=job,
                    prompt=prompt,
                    scene_number=scene.scene_number,
                    model_preference=image_model,
                    provider_id=job.image_provider_id,
                    reference_image_path=avatar_ref_path,
                    reference_image_strength=0.75,
                    label=f"image-s{scene.scene_number}",
                )
                scene.reference_image_path = image_path
                scene.status = "image_ready"
                # Auto-import to media library
                await _import_scene_asset(
                    db, job, scene.reference_image_path,
                    f"scene-{scene.scene_number}-image",
                    "image", scene.scene_number,
                )
                # Update progress: 20% → 40% spread across all scenes
                total = len(scenes)
                done = sum(1 for s in scenes if s.status == "image_ready")
                job.progress = min(20 + int(20 * done / max(total, 1)), 40)
            except Exception as exc:
                # If we were using a reference image, try T2I fallback
                if avatar_ref_path:
                    logger.warning(
                        "[image-s%s] img2img failed (retries exhausted), "
                        "falling back to T2I: %s",
                        scene.scene_number, exc,
                    )
                    try:
                        image_path, _media_id, _provider_id = await self._retry(
                            generate_image,
                            db=db,
                            job=job,
                            prompt=prompt,
                            scene_number=scene.scene_number,
                            model_preference=image_model,
                            provider_id=job.image_provider_id,
                            label=f"image-s{scene.scene_number}-t2i",
                        )
                        scene.reference_image_path = image_path
                        scene.status = "image_ready"
                        # Auto-import to media library
                        await _import_scene_asset(
                            db, job, scene.reference_image_path,
                            f"scene-{scene.scene_number}-image",
                            "image", scene.scene_number,
                        )
                        # Update progress
                        total = len(scenes)
                        done = sum(1 for s in scenes if s.status == "image_ready")
                        job.progress = min(20 + int(20 * done / max(total, 1)), 40)
                        continue  # Skip the failure marking below
                    except Exception as fallback_exc:
                        logger.error(
                            "[image-s%s] T2I fallback also failed: %s",
                            scene.scene_number, fallback_exc,
                        )

                # Original error handling (mark scene failed)
                logger.error(
                    "[image-s%s] generate_images failed: %s",
                    scene.scene_number, exc, exc_info=True,
                )
                scene.status = "failed"
                scene.error_message = str(exc)[:500]
            await db.commit()
        return context

    # ------------------------------------------------------------------
    # Stage: generate videos
    # ------------------------------------------------------------------

    async def generate_videos(
        self,
        db: AsyncSession,
        job: Job,
        scenes: list[VideoScene],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a video clip for each scene.

        For scenes ≤ 5s a single clip is generated.

        For scenes > 5s the scene is split into 5s sub-clips with
        chained last-frame seeding: each sub-clip uses the ~80% frame
        of the previous clip as its seed image, and the prompts evolve
        to tell a continuous story.  Sub-clips are merged with a 0.3s
        crossfade.
        """
        from app.services.media_generator import generate_video

        max_clip_s = 5          # Wan 2.2 practical max per clip
        crossfade_s = 0.3       # crossfade at sub-clip boundaries

        input_data = job.input_data or {}
        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        video_model = input_data.get("video_model")

        # Extract avatar context for sub-scene prompt hardening
        avatars = context.get("avatars", [])

        for scene in scenes:
            if scene.generated_video_path:
                continue

            scene_duration = scene.end_time - scene.start_time
            prompt = scene.visual_description or scene.lyrics_segment or ""

            # Inject object visual properties for this scene (short clip path)
            objects_ctx = context.get("objects", [])
            object_selections_ctx = context.get("object_selections", [])
            if objects_ctx and object_selections_ctx and prompt:
                scene_objs = [
                    sel for sel in object_selections_ctx
                    if scene.scene_number in sel.get("scenes", [])
                ]
                if scene_objs:
                    best = max(scene_objs, key=lambda s: s.get("importance_score", 0))
                    obj = next(
                        (o for o in objects_ctx if o.get("name") == best.get("object_name")),
                        None,
                    )
                    if obj and obj.get("primary_image_path") and obj.get("visual_properties"):
                        props_str = ", ".join(
                            f"{k}={v}" for k, v in obj["visual_properties"].items()
                        )
                        prompt = f"{prompt} [Object reference: {props_str}]"

            from app.database import ErrorOrigin, ErrorSeverity
            from app.services.error_capture import log_user_error
            from app.services.video_processor import InvalidVideoOutputError

            last_validation_error = None
            for attempt in range(4):
                try:
                    if scene_duration <= max_clip_s + 0.5:
                        # ── Short scene: single clip ──────────────────────
                        duration = max(2, int(scene_duration))
                        video_path, _, _, actual_duration, warning = await self._retry(
                            generate_video,
                            db=db, job=job, prompt=prompt,
                            scene_number=scene.scene_number,
                            reference_image_path=scene.reference_image_path,
                            provider_id=job.video_provider_id,
                            model_preference=video_model,
                            duration=duration, aspect_ratio=aspect_ratio,
                            label=f"video-s{scene.scene_number}",
                        )
                        scene.generated_video_path = video_path
                        scene.duration = actual_duration
                        if warning:
                            if scene.warnings is None:
                                scene.warnings = []
                            scene.warnings.append(warning)
                    else:
                        # ── Long scene: sub-clip chain ────────────────────
                        scene.generated_video_path, scene.duration = (
                            await self._generate_chained_subclips(
                                db=db, job=job, scene=scene,
                                scene_duration=scene_duration,
                                max_clip_s=max_clip_s,
                                crossfade_s=crossfade_s,
                                aspect_ratio=aspect_ratio,
                                avatars=avatars,
                                objects=context.get("objects", []),
                            )
                        )

                    scene.status = "video_ready"
                    scene.error_message = None
                    break
                except InvalidVideoOutputError as exc:
                    last_validation_error = exc
                    await log_user_error(
                        db,
                        user_id=job.user_id,
                        severity=ErrorSeverity.WARNING,
                        origin=ErrorOrigin.VIDEO_GENERATION,
                        message=str(exc),
                        details={
                            "actual_frames": exc.result.actual_frames,
                            "expected_frames": exc.result.expected_frames,
                            "retry_count": attempt,
                        },
                        source_id=scene.id,
                        source_type="scene",
                    )
                    if attempt >= 3:
                        break
                    delay = 10 * (2 ** attempt)
                    logger.warning(
                        "[video-s%s] Validation failed (attempt %d/4): %s — "
                        "retrying in %.0fs",
                        scene.scene_number, attempt + 1, exc, delay,
                    )
                    await asyncio.sleep(delay)
                except Exception as exc:
                    logger.error(
                        "[video-s%s] generate_videos failed: %s",
                        scene.scene_number, exc, exc_info=True,
                    )
                    scene.status = "failed"
                    scene.error_message = str(exc)[:500]
                    await log_user_error(
                        db,
                        user_id=job.user_id,
                        severity=ErrorSeverity.ERROR,
                        origin=ErrorOrigin.VIDEO_GENERATION,
                        message=str(exc),
                        details={
                            "scene_number": scene.scene_number,
                            "model": video_model,
                            "retry_count": attempt,
                        },
                        source_id=scene.id,
                        source_type="scene",
                    )
                    break

            if last_validation_error and scene.status != "video_ready":
                logger.error(
                    "[video-s%s] Video validation failed after 3 retries: %s",
                    scene.scene_number, last_validation_error,
                )
                scene.status = "failed"
                scene.error_message = str(last_validation_error)[:500]

            await db.commit()

        return context

    # ------------------------------------------------------------------
    # Sub-clip chaining for long scenes
    # ------------------------------------------------------------------

    async def _generate_chained_subclips(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        scene_duration: float,
        max_clip_s: int,
        crossfade_s: float,
        aspect_ratio: str,
        avatars: list[dict[str, Any]] | None = None,
        objects: list[dict[str, Any]] | None = None,
    ) -> tuple[str, float]:
        """Split a long scene into chained sub-clips.

        Returns (relative_video_path, actual_duration).
        """
        import math
        from pathlib import Path

        input_data = job.input_data or {}
        video_model = input_data.get("video_model")

        from app.config import get_settings
        from app.services.media_generator import (
            generate_video,
            get_scene_output_dir,
        )
        from app.services.video_processor import VideoProcessor

        settings = get_settings()
        storage = Path(settings.storage_path).resolve()
        output_dir = get_scene_output_dir(str(job.id), scene.scene_number)
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        num_clips = math.ceil(scene_duration / max_clip_s)
        prompts = await self._generate_sub_scene_prompts(
            db, job, scene, num_clips, avatars, objects,
        )

        sub_clip_paths: list[str] = []
        current_seed_path: str | None = scene.reference_image_path
        total_actual_duration = 0.0

        for i in range(num_clips):
            clip_duration = min(
                max_clip_s,
                scene_duration - i * max_clip_s,
            )
            clip_duration = max(2, int(clip_duration))

            sub_path, _, _, actual, warning = await self._retry(
                generate_video,
                db=db, job=job,
                prompt=prompts[i],
                scene_number=scene.scene_number,
                reference_image_path=current_seed_path,
                provider_id=job.video_provider_id,
                model_preference=video_model,
                duration=clip_duration,
                aspect_ratio=aspect_ratio,
                label=f"video-s{scene.scene_number}.{i+1}/{num_clips}",
            )
            sub_clip_paths.append(str(storage / sub_path))
            total_actual_duration += actual
            if warning:
                if scene.warnings is None:
                    scene.warnings = []
                scene.warnings.append(warning)

            # Extract ~80% frame for next clip's seed
            if i < num_clips - 1:
                seed_img = output_dir / f"seed_sub_{i + 1}.png"
                await VideoProcessor.extract_frame(
                    str(storage / sub_path), str(seed_img), ratio=0.8,
                )
                current_seed_path = str(
                    seed_img.relative_to(storage)
                )
                # Ensure consistent path separators
                current_seed_path = current_seed_path.replace("\\", "/")

        # Merge sub-clips with crossfade
        final_path = output_dir / "scene_video.mp4"
        if final_path.exists():
            final_path.unlink()  # Remove stale file from previous attempt
        if len(sub_clip_paths) == 1:
            import shutil
            shutil.copy(sub_clip_paths[0], final_path)
        else:
            await VideoProcessor.merge_with_crossfade(
                sub_clip_paths, str(final_path), crossfade_s,
            )

        relative = str(final_path.relative_to(storage))
        return relative, total_actual_duration

    async def _generate_sub_scene_prompts(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        num_clips: int,
        avatars: list[dict[str, Any]] | None = None,
        objects: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """Use the LLM to decompose a scene into evolving sub-clip prompts.

        Falls back to the original prompt + a continuation suffix if
        the LLM is unavailable.

        When avatar characters are provided, their descriptions are included
        in the system prompt so the LLM maintains character consistency across
        sub-clips.
        """
        original_prompt = scene.visual_description or scene.lyrics_segment or ""
        image_prompt = scene.image_prompt or original_prompt

        # Build character context string from avatars
        character_context = ""
        if avatars:
            active = [
                a for a in avatars
                if not a.get("deleted") and a.get("name")
            ]
            if active:
                chars = []
                for a in active:
                    parts = [a["name"]]
                    if a.get("gender"):
                        parts.append(f"({a['gender']})")
                    if a.get("role"):
                        parts.append(f"– {a['role']}")
                    if a.get("bio"):
                        parts.append(f": {a['bio']}")
                    chars.append(" ".join(parts))
                character_context = (
                    "CHARACTERS (must remain visually consistent across "
                    "all sub-clips):\n" + "\n".join(f"  – {c}" for c in chars)
                )

        # Build object context string from objects with reference images
        object_context = ""
        if objects:
            ref_objects = [
                o for o in objects
                if o.get("primary_image_path") and o.get("visual_properties")
            ]
            if ref_objects:
                obj_lines = []
                for o in ref_objects:
                    name = o.get("name", "unknown")
                    props = o.get("visual_properties", {})
                    props_str = ", ".join(f"{k}={v}" for k, v in props.items())
                    obj_lines.append(f"  – {name}: {props_str}")
                object_context = (
                    "OBJECT REFERENCES (maintain visual consistency for "
                    "these objects across all sub-clips):\n"
                    + "\n".join(obj_lines)
                )

        try:
            from app.services.llm_service import LLMClient
            llm = LLMClient()

            system = (
                "You are a video director. A scene is being split into "
                f"{num_clips} consecutive sub-clips. Write a brief "
                "visual prompt for each sub-clip that tells a continuous, "
                "evolving story. Each prompt should describe what happens "
                "in that segment and flow naturally into the next. "
                "Keep each prompt under 100 words. "
                "Output ONLY a JSON array of strings."
            )
            if character_context:
                system = character_context + "\n\n" + system
            if object_context:
                system = object_context + "\n\n" + system

            user = (
                f"Original scene description: {original_prompt}\n"
                f"Original image prompt: {image_prompt}\n"
                f"Scene mood: {scene.mood}\n"
                f"Split into {num_clips} consecutive sub-clips."
            )
            response = await llm.generate(user, system=system)
            import json
            prompts = json.loads(response)
            if isinstance(prompts, list) and len(prompts) == num_clips:
                return [str(p) for p in prompts]
        except Exception:
            pass

        # Fallback: reuse original prompt with continuation markers
        prompts = []
        for i in range(num_clips):
            if i == 0:
                prompts.append(image_prompt)
            else:
                prompts.append(
                    f"Continuation of the scene: {original_prompt}. "
                    f"Part {i + 1} of {num_clips}."
                )
        return prompts

    # ------------------------------------------------------------------
    # Stage: render
    # ------------------------------------------------------------------

    async def render(
        self,
        db: AsyncSession,
        job: Job,
        scenes: list[VideoScene],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Final rendering: merge clips, add audio, generate preview.

        The default implementation concatenates all scene videos, adds
        the audio from ``job.input_data["audio_file"]`` (if present),
        and generates a low-res preview.
        """
        import shutil
        from pathlib import Path

        from app.config import get_settings
        from app.services.video_processor import VideoProcessor

        settings = get_settings()
        storage_path = Path(settings.storage_path).resolve()
        output_dir = storage_path / "output" / str(job.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Check if any scene needs padding
        any_needs_padding = False
        for scene in scenes:
            if scene.warnings:
                for w in scene.warnings:
                    if "aspect ratio" in w.lower():
                        any_needs_padding = True
                        break
            if any_needs_padding:
                break

        input_data = job.input_data or {}
        target_aspect = input_data.get("aspect_ratio", "16:9")

        # Collect scene video paths
        segment_paths: list[str] = []
        for scene in scenes:
            if not scene.generated_video_path:
                continue
            full = storage_path / scene.generated_video_path
            if full.exists():
                if any_needs_padding:
                    padded_path = output_dir / f"padded_scene_{scene.scene_number}.mp4"
                    await VideoProcessor.pad_to_aspect_ratio(
                        str(full), str(padded_path), target_aspect
                    )
                    scene.generated_video_path = str(padded_path.relative_to(storage_path))
                    segment_paths.append(str(padded_path))
                else:
                    segment_paths.append(str(full))

        if not segment_paths:
            raise RuntimeError("No scene videos to render")

        merged_path = output_dir / "merged.mp4"
        if len(segment_paths) == 1:
            shutil.copy(segment_paths[0], merged_path)
        else:
            await VideoProcessor.merge_videos(segment_paths, str(merged_path))

        # Add audio if available
        final_path = output_dir / "final.mp4"
        input_data = job.input_data or {}
        audio_file = input_data.get("audio_file") or context.get("audio_file")
        bgm_file = context.get("background_music")
        bgm_volume = context.get("background_music_volume", 0.3)

        if audio_file and bgm_file:
            # Mix narration + background music
            audio_path = storage_path / audio_file
            bgm_path = Path(bgm_file)
            if audio_path.exists() and bgm_path.exists():
                mixed_audio = output_dir / "mixed_audio.mp3"
                await VideoProcessor.mix_audio(
                    [str(audio_path), str(bgm_path)],
                    str(mixed_audio),
                    volumes=[context.get("audio_volume", 1.0), bgm_volume],
                )
                await VideoProcessor.add_audio(
                    str(merged_path), str(mixed_audio), str(final_path),
                    audio_volume=1.0,
                )
            elif audio_path.exists():
                await VideoProcessor.add_audio(
                    str(merged_path), str(audio_path), str(final_path),
                    audio_volume=context.get("audio_volume", 1.0),
                )
            else:
                shutil.copy(str(merged_path), str(final_path))
        elif audio_file:
            audio_path = storage_path / audio_file
            if audio_path.exists():
                await VideoProcessor.add_audio(
                    str(merged_path), str(audio_path), str(final_path),
                    audio_volume=context.get("audio_volume", 1.0),
                )
            else:
                shutil.copy(str(merged_path), str(final_path))
        elif bgm_file:
            bgm_path = Path(bgm_file)
            if bgm_path.exists():
                await VideoProcessor.add_audio(
                    str(merged_path), str(bgm_path), str(final_path),
                    audio_volume=bgm_volume,
                )
            else:
                shutil.copy(str(merged_path), str(final_path))
        else:
            shutil.copy(str(merged_path), str(final_path))

        # Preview
        preview_path = output_dir / "preview.mp4"
        try:
            await VideoProcessor.generate_preview(
                str(final_path), str(preview_path),
                width=854, height=480, fps=15, quality=28,
            )
        except Exception:
            pass

        job.output_path = str(final_path.relative_to(storage_path))
        if preview_path.exists():
            job.preview_path = str(preview_path.relative_to(storage_path))

        return {
            "output_path": job.output_path,
            "preview_path": job.preview_path,
        }

    # ------------------------------------------------------------------
    # Per-scene re-render hooks
    # ------------------------------------------------------------------

    async def rerender_scene_image(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        context: dict[str, Any],
    ) -> str | None:
        """Re-generate a single scene's image.  Returns relative path."""
        from app.services.media_generator import generate_image

        prompt = scene.image_prompt or scene.visual_description or ""
        if not prompt:
            return None
        input_data = job.input_data or {}
        image_path, _mid, _pid = await self._retry(
            generate_image,
            db=db, job=job, prompt=prompt,
            scene_number=scene.scene_number,
            provider_id=job.image_provider_id,
            model_preference=input_data.get("image_model"),
            label=f"rerender-image-s{scene.scene_number}",
        )
        scene.reference_image_path = image_path
        scene.status = "image_ready"
        scene.error_message = None
        await db.commit()
        return image_path

    async def rerender_scene_video(
        self,
        db: AsyncSession,
        job: Job,
        scene: VideoScene,
        context: dict[str, Any],
    ) -> str | None:
        """Re-generate a single scene's video.  Returns relative path."""
        scene_duration = scene.end_time - scene.start_time
        input_data = job.input_data or {}
        if scene_duration > 5.5:
            path, duration = await self._generate_chained_subclips(
                db=db, job=job, scene=scene,
                scene_duration=scene_duration,
                max_clip_s=5, crossfade_s=0.3,
                aspect_ratio=(job.input_data or {}).get("aspect_ratio", "16:9"),
            )
            scene.generated_video_path = path
            scene.duration = duration
        else:
            from app.services.media_generator import generate_video
            duration = max(2, int(scene_duration))
            prompt = scene.visual_description or scene.lyrics_segment or ""
            input_data = job.input_data or {}
            video_path, _mid, _pid, actual_duration, warning = await self._retry(
                generate_video,
                db=db, job=job, prompt=prompt,
                scene_number=scene.scene_number,
                reference_image_path=scene.reference_image_path,
                provider_id=job.video_provider_id,
                model_preference=input_data.get("video_model"),
                duration=duration,
                aspect_ratio=input_data.get("aspect_ratio", "16:9"),
                label=f"rerender-video-s{scene.scene_number}",
            )
            scene.generated_video_path = video_path
            scene.duration = actual_duration
            if warning:
                if scene.warnings is None:
                    scene.warnings = []
                scene.warnings.append(warning)

        scene.status = "video_ready"
        scene.error_message = None
        await db.commit()
        await _import_scene_asset(db, job, scene.generated_video_path, f"scene-{scene.scene_number}-video", "video", scene.scene_number)
        return scene.generated_video_path

    # ------------------------------------------------------------------
    # UI metadata
    # ------------------------------------------------------------------

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
