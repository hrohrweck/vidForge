"""Built-in tool definitions and registry."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, Style, Template, UserSettings
from app.models.media import MediaAsset
from app.models.media import FileType
from app.plugins.registry import get_all_plugins
from app.services.llm_service import LLMClient
from app.api.models import get_available_models as _get_available_models


@dataclass
class ToolContext:
    """Execution context passed to every tool handler."""

    user_id: str
    db: AsyncSession | None = None
    request_id: str = ""


AsyncHandler = Callable[[ToolContext, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


@dataclass
class ToolDefinition:
    """Definition of a callable tool available to the chatbot LLM."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: AsyncHandler


class ToolRegistry:
    """Registry for built-in chatbot tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Return a tool by name, or None if not found."""
        return self._tools.get(name)

    def list_all(self) -> dict[str, ToolDefinition]:
        """Return a copy of all registered tools."""
        return dict(self._tools)

    def to_openai_format(self) -> list[dict[str, Any]]:
        """Return tools in OpenAI ``functions`` format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools.values()
        ]


async def _handle_create_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a new video generation job."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}

    template = args.get("template")
    prompt = args.get("prompt")
    style = args.get("style")
    image_model = args.get("image_model")
    video_model = args.get("video_model")
    duration_seconds = args.get("duration_seconds")
    aspect_ratio = args.get("aspect_ratio")
    reference_image_id = args.get("reference_image_id")

    if not template:
        return {"error": "missing_argument", "message": "'template' is required"}
    if not prompt:
        return {"error": "missing_argument", "message": "'prompt' is required"}

    db: AsyncSession = ctx.db

    template_obj = None
    try:
        template_uuid = UUID(template)
        result = await db.execute(select(Template).where(Template.id == template_uuid))
        template_obj = result.scalar_one_or_none()
    except ValueError:
        result = await db.execute(select(Template).where(Template.name == template))
        template_obj = result.scalar_one_or_none()

    if template_obj is None:
        return {"error": "not_found", "message": f"Template '{template}' not found"}

    user_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == UUID(ctx.user_id))
    )
    user_settings = user_result.scalar_one_or_none()
    auto_create = True
    if user_settings and user_settings.preferences:
        auto_create = user_settings.preferences.get("auto_create_jobs", True)

    input_data: dict[str, Any] = {"prompt": prompt}
    if style:
        input_data["style"] = style
    if image_model:
        input_data["image_model"] = image_model
    if video_model:
        input_data["video_model"] = video_model
    if duration_seconds is not None:
        input_data["duration_seconds"] = duration_seconds
    if aspect_ratio:
        input_data["aspect_ratio"] = aspect_ratio
    if reference_image_id:
        input_data["reference_image_id"] = reference_image_id

    if not auto_create:
        return {
            "action": "draft",
            "payload": {
                "template_id": str(template_obj.id),
                "title": prompt[:50] if prompt else "Untitled Video",
                "input_data": input_data,
            },
        }

    job = Job(
        user_id=UUID(ctx.user_id),
        template_id=template_obj.id,
        title=prompt[:50] if prompt else "Untitled Video",
        input_data=input_data,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {
        "job_id": str(job.id),
        "status": job.status,
        "monitor_url": f"/api/jobs/{job.id}",
    }


async def _handle_list_templates(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List available template plugins."""
    plugins = get_all_plugins()
    templates = []
    for pid, plugin in plugins.items():
        templates.append(
            {
                "id": pid,
                "name": plugin.display_name,
                "description": plugin.description,
            }
        )
    return {"templates": templates}


async def _handle_list_styles(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List available styles from the database."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}

    db: AsyncSession = ctx.db
    result = await db.execute(select(Style).order_by(Style.name))
    styles = []
    for style in result.scalars().all():
        styles.append(
            {
                "id": str(style.id),
                "name": style.name,
                "category": style.category,
            }
        )
    return {"styles": styles}


async def _handle_list_models(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List available AI models, optionally filtered by modality."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}
    models = await _get_available_models(ctx.db)
    modality = args.get("modality")

    if modality:
        key = f"{modality}_models"
        if key in models:
            return {"modality": modality, "models": models[key]}
        return {"error": "invalid_modality", "message": f"Unknown modality '{modality}'"}

    return {
        "image_models": models.get("image_models", []),
        "video_models": models.get("video_models", []),
        "text_models": models.get("text_models", []),
    }


async def _handle_get_job_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get the status of a specific job."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}

    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    db: AsyncSession = ctx.db
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        return {"error": "invalid_argument", "message": f"'job_id' must be a valid UUID"}

    result = await db.execute(
        select(Job).where(Job.id == job_uuid, Job.user_id == UUID(ctx.user_id))
    )
    job = result.scalar_one_or_none()
    if job is None:
        return {"error": "not_found", "message": f"Job '{job_id}' not found"}

    return {
        "job_id": str(job.id),
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "title": job.title,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
    }


async def _handle_list_user_jobs(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List jobs for the current user."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}

    db: AsyncSession = ctx.db
    limit = args.get("limit", 10)
    status = args.get("status")

    query = select(Job).where(Job.user_id == UUID(ctx.user_id)).order_by(Job.created_at.desc())
    if status:
        query = query.where(Job.status == status)
    query = query.limit(limit)

    result = await db.execute(query)
    jobs = []
    for job in result.scalars().all():
        jobs.append(
            {
                "job_id": str(job.id),
                "status": job.status,
                "stage": job.stage,
                "progress": job.progress,
                "title": job.title,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
        )
    return {"jobs": jobs, "count": len(jobs)}


async def _handle_search_media_library(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Search the user's media library."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}

    query = args.get("query")
    file_type = args.get("file_type")

    if not query:
        return {"error": "missing_argument", "message": "'query' is required"}

    db: AsyncSession = ctx.db
    db_query = select(MediaAsset).where(MediaAsset.user_id == UUID(ctx.user_id))

    search_term = f"%{query}%"
    db_query = db_query.where(MediaAsset.name.ilike(search_term))

    if file_type:
        db_query = db_query.where(MediaAsset.file_type == file_type)

    db_query = db_query.order_by(MediaAsset.created_at.desc()).limit(20)
    result = await db.execute(db_query)
    assets = []
    for asset in result.scalars().all():
        assets.append(
            {
                "id": str(asset.id),
                "name": asset.name,
                "file_type": asset.file_type,
                "file_path": asset.file_path,
                "preview_path": asset.preview_path,
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
            }
        )
    return {"assets": assets, "count": len(assets)}


async def _handle_enhance_prompt(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Enhance a video generation prompt using an LLM."""
    prompt = args.get("prompt")
    target = args.get("target", "video")

    if not prompt:
        return {"error": "missing_argument", "message": "'prompt' is required"}

    llm = LLMClient()
    try:
        system = (
            "You are a prompt enhancer for AI video generation. "
            "Improve the user's prompt with visual details, lighting, camera angles, and mood. "
            "Keep the core idea intact. Output only the enhanced prompt, nothing else."
        )
        enhanced = await llm.generate(
            prompt=f"Enhance this {target} generation prompt:\n\n{prompt}",
            system=system,
            max_tokens=256,
            temperature=0.7,
        )
        return {"original_prompt": prompt, "enhanced_prompt": enhanced.strip()}
    except Exception as exc:
        return {"error": "enhancement_failed", "message": str(exc)}
    finally:
        await llm.close()


async def _handle_estimate_job_cost(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Estimate the cost of a video generation job."""
    template = args.get("template")
    image_model = args.get("image_model")
    video_model = args.get("video_model")
    duration_seconds = args.get("duration_seconds")

    if duration_seconds is None:
        return {"error": "missing_argument", "message": "'duration_seconds' is required"}

    image_model_costs = {
        "flux1-schnell": 0.5,
        "sdxl": 0.3,
        "poe:flux": 0.8,
        "poe:sd3": 0.7,
    }
    video_model_costs = {
        "wan2.2": 2.0,
        "ltx2.3": 3.5,
        "ltx2.3-fast": 2.5,
        "poe:wan": 4.0,
    }

    num_clips = max(1, int(duration_seconds / 5))

    image_cost = image_model_costs.get(image_model, 0.5) * num_clips
    video_cost = video_model_costs.get(video_model, 2.0) * num_clips
    base_cost = 0.5

    estimated_cost = round(base_cost + image_cost + video_cost, 2)

    return {
        "template": template,
        "image_model": image_model,
        "video_model": video_model,
        "duration_seconds": duration_seconds,
        "estimated_clips": num_clips,
        "estimated_cost": estimated_cost,
        "currency": "credits",
    }


def create_builtin_registry() -> ToolRegistry:
    """Create and populate a ToolRegistry with all built-in tools."""
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="create_job",
            description="Create a new video generation job. If the user has auto_create_jobs disabled, returns a draft payload instead.",
            input_schema={
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "Template ID or name"},
                    "prompt": {"type": "string", "description": "Video generation prompt"},
                    "style": {"type": "string", "description": "Visual style name"},
                    "image_model": {"type": "string", "description": "Image generation model ID"},
                    "video_model": {"type": "string", "description": "Video generation model ID"},
                    "duration_seconds": {"type": "number", "description": "Target duration in seconds"},
                    "aspect_ratio": {"type": "string", "description": "Aspect ratio (e.g. 16:9)"},
                    "reference_image_id": {"type": "string", "description": "Optional reference image asset ID"},
                },
                "required": ["template", "prompt"],
            },
            handler=_handle_create_job,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_templates",
            description="List all available video generation template plugins.",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=_handle_list_templates,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_styles",
            description="List all available visual styles.",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=_handle_list_styles,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_models",
            description="List available AI models. Optionally filter by modality (image, video, text).",
            input_schema={
                "type": "object",
                "properties": {
                    "modality": {"type": "string", "description": "Filter by modality: image, video, or text"},
                },
            },
            handler=_handle_list_models,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_job_status",
            description="Get the current status and progress of a specific job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                },
                "required": ["job_id"],
            },
            handler=_handle_get_job_status,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_user_jobs",
            description="List jobs created by the current user, optionally filtered by status.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum number of jobs to return", "default": 10},
                    "status": {"type": "string", "description": "Filter by job status (pending, processing, completed, failed)"},
                },
            },
            handler=_handle_list_user_jobs,
        )
    )

    registry.register(
        ToolDefinition(
            name="search_media_library",
            description="Search the user's media library by name.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                    "file_type": {"type": "string", "description": "Optional file type filter (image, video, audio, markdown)"},
                },
                "required": ["query"],
            },
            handler=_handle_search_media_library,
        )
    )

    registry.register(
        ToolDefinition(
            name="enhance_prompt",
            description="Enhance a video generation prompt using an LLM for better visual quality.",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The prompt to enhance"},
                    "target": {"type": "string", "description": "Target type: video or image", "default": "video"},
                },
                "required": ["prompt"],
            },
            handler=_handle_enhance_prompt,
        )
    )

    registry.register(
        ToolDefinition(
            name="estimate_job_cost",
            description="Estimate the cost (in credits) of a video generation job based on parameters.",
            input_schema={
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "Template ID or name"},
                    "image_model": {"type": "string", "description": "Image model ID"},
                    "video_model": {"type": "string", "description": "Video model ID"},
                    "duration_seconds": {"type": "number", "description": "Target duration in seconds"},
                },
                "required": ["duration_seconds"],
            },
            handler=_handle_estimate_job_cost,
        )
    )

    return registry


async def dispatch(
    name: str,
    args: dict[str, Any],
    context: ToolContext,
    registry: ToolRegistry,
) -> dict[str, Any]:
    """Call the registered tool handler and return its result.

    All exceptions are caught and returned as a standardized error dict so they
    never propagate to the LLM.
    """
    tool = registry.get(name)
    if tool is None:
        available = list(registry.list_all().keys())
        return {
            "error": "unknown_tool",
            "message": f"No tool named '{name}'",
            "available_tools": available,
        }

    try:
        return await tool.handler(context, args)
    except Exception as exc:
        return {
            "error": "handler_error",
            "message": f"Tool '{name}' failed: {type(exc).__name__}: {exc}",
            "available_tools": list(registry.list_all().keys()),
        }
