"""Input enrichment, object-reference, and scene re-render helpers for plugins."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import Job, VideoScene

_module_logger = logging.getLogger(__name__)


class _BaseLoggerProxy:
    def __getattr__(self, name: str) -> Any:
        base_module = sys.modules.get("app.plugins.base")
        return getattr(getattr(base_module, "logger", _module_logger), name)


logger = _BaseLoggerProxy()


async def _import_scene_asset(*args: Any, **kwargs: Any) -> Any:
    base_module = sys.modules.get("app.plugins.base")
    target = getattr(base_module, "_import_scene_asset", None)
    if target is not None and target is not _import_scene_asset:
        return await target(*args, **kwargs)
    return None


async def _generate_llm_text(
    llm: Any,
    *,
    prompt: str,
    system: str,
    model: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    """Generate text from either legacy LLMClient or registry LLMProvider."""
    kwargs: dict[str, Any] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature

    if hasattr(llm, "generate"):
        return await llm.generate(prompt=prompt, system=system, **kwargs)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    chunks: list[str] = []
    async for chunk in llm.chat(messages, model=model, **kwargs):
        if getattr(chunk, "type", None) == "text" and getattr(chunk, "content", None):
            chunks.append(chunk.content)
    return "".join(chunks)


class EnrichmentMixin:
    """Default enrichment and re-render behavior shared by template plugins."""

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
        from app.services.llm_service import resolve_llm
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
            text_model = input_data.get("text_model")
            llm = await resolve_llm(text_model or "", db)
            response = await _generate_llm_text(
                llm,
                prompt=f"Video prompt: {prompt}",
                system=system,
                model=text_model or "",
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
                image_path, _media_id, _provider_id = await cast(Any, self)._retry(
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
        image_path, _mid, _pid = await cast(Any, self)._retry(
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
            path, duration = await cast(Any, self)._generate_chained_subclips(
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
            video_path, _mid, _pid, actual_duration, warning = await cast(Any, self)._retry(
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
