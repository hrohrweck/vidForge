"""Built-in tool definitions and registry."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Job, Project, Template
from app.services.llm_service import LLMClient


@dataclass
class ToolContext:
    """Execution context passed to every tool handler."""

    user_id: str
    db: AsyncSession | None = None
    request_id: str = ""
    conversation_id: str | None = None
    message_id: str | None = None


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


async def _resolve_attachment_image_url(ctx: ToolContext) -> str:
    from app.database import Message

    if not (ctx.conversation_id and ctx.db is not None):
        return ""
    result = await ctx.db.execute(
        select(Message.attachments)
        .where(Message.conversation_id == UUID(ctx.conversation_id))
        .where(Message.role == "user")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    attachments = result.scalar()
    if attachments:
        for att in attachments:
            if att.get("kind") == "image":
                return att.get("url", "")
    return ""


async def _handle_create_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a new video generation job."""
    template = args.get("template")
    prompt = args.get("prompt")
    if not template:
        return {"error": "missing_argument", "message": "'template' is required"}
    if not prompt:
        return {"error": "missing_argument", "message": "'prompt' is required"}

    payload: dict[str, Any] = {
        "title": prompt[:50] if prompt else "Untitled Video",
        "input_data": {"prompt": prompt},
    }

    try:
        UUID(template)
        payload["template_id"] = template
    except ValueError:
        # The LLM sometimes passes a template name instead of a UUID.
        # Resolve it to the matching builtin template ID.
        if ctx.db is not None:
            result = await ctx.db.execute(
                select(Template.id)
                .where(Template.name.ilike(template))
                .limit(1)
            )
            template_id = result.scalar_one_or_none()
            if template_id is not None:
                payload["template_id"] = str(template_id)
            else:
                payload["template_id"] = template
        else:
            payload["template_id"] = template

    if "reference_image_url" not in args:
        url = await _resolve_attachment_image_url(ctx)
        if url:
            args["reference_image_url"] = url

    for key in ("style", "image_model", "video_model", "aspect_ratio", "reference_image_id", "reference_image_url"):
        if key in args:
            payload["input_data"][key] = args[key]
    if "duration_seconds" in args:
        payload["input_data"]["duration_seconds"] = args["duration_seconds"]

    # Resolve provider_id for explicitly chosen models so the pipeline
    # can route unambiguously even when the model_id is not globally unique.
    if ctx.db is not None:
        from app.services.model_config_service import ModelConfigService

        for model_key, provider_key in (("image_model", "image_provider_id"), ("video_model", "video_provider_id")):
            model_id = payload["input_data"].get(model_key)
            if model_id and provider_key not in payload["input_data"]:
                config = await ModelConfigService.resolve_model_config(ctx.db, model_id)
                if config is not None:
                    payload["input_data"][provider_key] = str(config.provider_id)
    if ctx.conversation_id:
        payload["chat_conversation_id"] = ctx.conversation_id
    if ctx.message_id:
        payload["chat_message_id"] = ctx.message_id

    # Let the jobs endpoint auto-start by default so the chat-created job
    # actually enters the pipeline instead of remaining pending.
    payload.setdefault("auto_start", True)

    from app.chatbot.api_tools import call_user_api

    result = await call_user_api(ctx, "POST", "/jobs", json_data=payload)
    if isinstance(result, dict) and "id" in result and "job_id" not in result:
        result["job_id"] = result["id"]
    return result


async def _handle_list_templates(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List available template plugins."""
    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", "/templates")


async def _handle_get_template(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get a single template by ID."""
    template_id = args.get("id")
    if not template_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", f"/templates/{template_id}")


async def _handle_create_template(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a new template."""
    name = args.get("name")
    config = args.get("config")
    if not name:
        return {"error": "missing_argument", "message": "'name' is required"}
    if not config:
        return {"error": "missing_argument", "message": "'config' is required"}

    payload: dict[str, Any] = {"name": name, "config": config}
    if "description" in args:
        payload["description"] = args["description"]

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/templates", json_data=payload)


async def _handle_update_template(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Update an existing template."""
    template_id = args.get("id")
    if not template_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    payload: dict[str, Any] = {}
    if "name" in args:
        payload["name"] = args["name"]
    if "description" in args:
        payload["description"] = args["description"]
    if "config" in args:
        payload["config"] = args["config"]

    if not payload:
        return {"error": "missing_argument", "message": "No fields to update"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "PUT", f"/templates/{template_id}", json_data=payload)


async def _handle_delete_template(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Delete a template by ID."""
    template_id = args.get("id")
    if not template_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "DELETE", f"/templates/{template_id}")


async def _handle_list_styles(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List available styles."""
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {}
    if "category" in args:
        params["category"] = args["category"]

    return await call_user_api(ctx, "GET", "/styles", params=params)


async def _handle_get_style(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get a single style by ID."""
    style_id = args.get("id")
    if not style_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", f"/styles/{style_id}")


async def _handle_create_style(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a new visual style."""
    name = args.get("name")
    if not name:
        return {"error": "missing_argument", "message": "'name' is required"}

    payload: dict[str, Any] = {"name": name}
    if "category" in args:
        payload["category"] = args["category"]
    if "params" in args:
        payload["params"] = args["params"]

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/styles", json_data=payload)


async def _handle_update_style(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Update an existing style."""
    style_id = args.get("id")
    if not style_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    payload: dict[str, Any] = {}
    if "name" in args:
        payload["name"] = args["name"]
    if "category" in args:
        payload["category"] = args["category"]
    if "params" in args:
        payload["params"] = args["params"]

    if not payload:
        return {"error": "missing_argument", "message": "No fields to update"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "PUT", f"/styles/{style_id}", json_data=payload)


async def _handle_delete_style(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Delete a style by ID."""
    style_id = args.get("id")
    if not style_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "DELETE", f"/styles/{style_id}")


async def _handle_list_models(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List available AI models, optionally filtered by modality."""
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {}
    if "modality" in args:
        params["modality"] = args["modality"]

    return await call_user_api(ctx, "GET", "/models", params=params)


async def _handle_list_avatars(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List avatars for the current user."""
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {}
    if "skip" in args:
        params["skip"] = args["skip"]
    if "limit" in args:
        params["limit"] = args["limit"]

    return await call_user_api(ctx, "GET", "/avatars", params=params)


async def _handle_get_avatar(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get a single avatar by ID."""
    avatar_id = args.get("id")
    if not avatar_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", f"/avatars/{avatar_id}")


async def _handle_create_avatar(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a new avatar."""
    name = args.get("name")
    if not name:
        return {"error": "missing_argument", "message": "'name' is required"}

    payload: dict[str, Any] = {"name": name}
    if "gender" in args:
        payload["gender"] = args["gender"]
    if "bio" in args:
        payload["bio"] = args["bio"]
    if "consistency_strategy" in args:
        payload["consistency_strategy"] = args["consistency_strategy"]

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/avatars", json_data=payload)


async def _handle_update_avatar(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Update an existing avatar."""
    avatar_id = args.get("id")
    if not avatar_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    payload: dict[str, Any] = {}
    for field in ("name", "gender", "bio", "consistency_strategy", "primary_image_id"):
        if field in args:
            payload[field] = args[field]

    if not payload:
        return {"error": "missing_argument", "message": "No fields to update"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "PUT", f"/avatars/{avatar_id}", json_data=payload)


async def _handle_delete_avatar(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Delete an avatar by ID."""
    avatar_id = args.get("id")
    if not avatar_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "DELETE", f"/avatars/{avatar_id}")


async def _handle_get_audio_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Check whether the AudioCraft/MusicGen service is available."""
    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", "/audio/status")


async def _handle_generate_music(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Generate background music using AudioCraft/MusicGen."""
    prompt = args.get("prompt")
    if not prompt:
        return {"error": "missing_argument", "message": "'prompt' is required"}

    payload: dict[str, Any] = {"prompt": prompt}
    if "duration" in args:
        payload["duration"] = args["duration"]
    if "output_format" in args:
        payload["output_format"] = args["output_format"]

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/audio/generate-music", json_data=payload)


async def _handle_upload_image_url(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Upload an image from a URL or existing storage path. Returns the file URL only."""
    url = args.get("url")
    if not url:
        return {"error": "missing_argument", "message": "'url' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/uploads/image-url", json_data={"url": url})


async def _handle_upload_video_url(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Upload a video from a URL or existing storage path. Returns the file URL only."""
    url = args.get("url")
    if not url:
        return {"error": "missing_argument", "message": "'url' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/uploads/video-url", json_data={"url": url})


async def _handle_upload_audio_url(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Upload an audio file from a URL or existing storage path. Returns the file URL only."""
    url = args.get("url")
    if not url:
        return {"error": "missing_argument", "message": "'url' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/uploads/audio-url", json_data={"url": url})


async def _handle_get_user_settings(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get the current user's settings."""
    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", "/users/settings")


async def _handle_update_user_settings(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Update the current user's settings."""
    payload: dict[str, Any] = {}
    for field in ("default_style_id", "storage_backend", "storage_config", "preferences"):
        if field in args:
            payload[field] = args[field]

    if not payload:
        return {"error": "missing_argument", "message": "No fields to update"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "PUT", "/users/settings", json_data=payload)


async def _handle_get_job_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get the status of a specific job."""
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", f"/jobs/{job_id}")


async def _handle_list_user_jobs(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List jobs for the current user."""
    params: dict[str, Any] = {}
    limit = args.get("limit")
    if limit is not None:
        params["limit"] = limit
    status = args.get("status")
    if status:
        params["status"] = status

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", "/jobs", params=params)


async def _handle_start_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Start a pending job."""
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", f"/jobs/{job_id}/start")


async def _handle_retry_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Retry a failed or completed job."""
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", f"/jobs/{job_id}/retry")


async def _handle_delete_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Delete a job by ID."""
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "DELETE", f"/jobs/{job_id}")


async def _handle_update_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Update a job's input_data."""
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    payload: dict[str, Any] = {}
    if "input_data" in args:
        payload["input_data"] = args["input_data"]

    if not payload:
        return {"error": "missing_argument", "message": "No fields to update"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "PATCH", f"/jobs/{job_id}", json_data=payload)


async def _handle_download_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Return a download URL for a completed job's output video."""
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    result = await call_user_api(ctx, "GET", f"/jobs/{job_id}/download")
    if "error" in result:
        return result

    # The endpoint returns a FileResponse; we surface a URL instead of binary.
    return {
        "download_url": f"/api/jobs/{job_id}/download",
    }


async def _handle_batch_create_jobs(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create multiple jobs in a batch."""
    template_id = args.get("template_id")
    jobs = args.get("jobs")
    if not template_id:
        return {"error": "missing_argument", "message": "'template_id' is required"}
    if not jobs:
        return {"error": "missing_argument", "message": "'jobs' is required"}

    payload: dict[str, Any] = {
        "template_id": template_id,
        "jobs": jobs,
    }
    if "project_id" in args:
        payload["project_id"] = args["project_id"]
    if "auto_start" in args:
        payload["auto_start"] = args["auto_start"]
    if "provider_preference" in args:
        payload["provider_preference"] = args["provider_preference"]
    if "model_preference" in args:
        payload["model_preference"] = args["model_preference"]
    if ctx.conversation_id:
        payload["chat_conversation_id"] = ctx.conversation_id
    if ctx.message_id:
        payload["chat_message_id"] = ctx.message_id

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", "/jobs/batch", json_data=payload)


async def _handle_search_media_library(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    query = args.get("query")
    if not query:
        return {"error": "missing_argument", "message": "'query' is required"}

    params: dict[str, Any] = {"search": query, "limit": 20}
    if "file_type" in args:
        params["file_type"] = args["file_type"]

    return await call_user_api(ctx, "GET", "/media/assets", params=params)


async def _handle_list_folders(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {}
    if "parent_id" in args:
        params["parent_id"] = args["parent_id"]
    return await call_user_api(ctx, "GET", "/media/folders", params=params)


async def _handle_create_folder(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    name = args.get("name")
    if not name:
        return {"error": "missing_argument", "message": "'name' is required"}
    payload: dict[str, Any] = {"name": name}
    if "parent_id" in args:
        payload["parent_id"] = args["parent_id"]
    return await call_user_api(ctx, "POST", "/media/folders", json_data=payload)


async def _handle_update_folder(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    folder_id = args.get("id")
    if not folder_id:
        return {"error": "missing_argument", "message": "'id' is required"}
    patch: dict[str, Any] = {}
    if "name" in args:
        patch["name"] = args["name"]
    if "parent_id" in args:
        patch["parent_id"] = args["parent_id"]
    if not patch:
        return {"error": "missing_argument", "message": "No fields to update"}
    return await call_user_api(ctx, "PATCH", f"/media/folders/{folder_id}", json_data=patch)


async def _handle_delete_folder(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    folder_id = args.get("id")
    if not folder_id:
        return {"error": "missing_argument", "message": "'id' is required"}
    return await call_user_api(ctx, "DELETE", f"/media/folders/{folder_id}")


async def _handle_folder_tree(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", "/media/folders/tree")


async def _handle_list_assets(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {
        "limit": args.get("limit", 20),
        "offset": args.get("offset", 0),
    }
    if "folder_id" in args:
        params["folder_id"] = args["folder_id"]
    if "file_type" in args:
        params["file_type"] = args["file_type"]
    if "search" in args:
        params["search"] = args["search"]
    if "tag_ids" in args:
        params["tag_ids"] = args["tag_ids"]
    return await call_user_api(ctx, "GET", "/media/assets", params=params)


async def _handle_get_asset(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    asset_id = args.get("id")
    if not asset_id:
        return {"error": "missing_argument", "message": "'id' is required"}
    return await call_user_api(ctx, "GET", f"/media/assets/{asset_id}")


async def _handle_update_asset(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    asset_id = args.get("id")
    if not asset_id:
        return {"error": "missing_argument", "message": "'id' is required"}
    patch: dict[str, Any] = {}
    if "name" in args:
        patch["name"] = args["name"]
    if "folder_id" in args:
        patch["folder_id"] = args["folder_id"]
    if "project_id" in args:
        patch["project_id"] = args["project_id"]
    if "tag_ids" in args:
        patch["tag_ids"] = args["tag_ids"]
    if not patch:
        return {"error": "missing_argument", "message": "No fields to update"}
    return await call_user_api(ctx, "PATCH", f"/media/assets/{asset_id}", json_data=patch)


async def _handle_delete_asset(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    asset_id = args.get("id")
    if not asset_id:
        return {"error": "missing_argument", "message": "'id' is required"}
    return await call_user_api(ctx, "DELETE", f"/media/assets/{asset_id}")


async def _handle_list_tags(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", "/media/tags")


async def _handle_create_tag(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    name = args.get("name")
    if not name:
        return {"error": "missing_argument", "message": "'name' is required"}
    payload: dict[str, Any] = {"name": name}
    if "color" in args:
        payload["color"] = args["color"]
    return await call_user_api(ctx, "POST", "/media/tags", json_data=payload)


async def _handle_update_tag(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    tag_id = args.get("id")
    if not tag_id:
        return {"error": "missing_argument", "message": "'id' is required"}
    patch: dict[str, Any] = {}
    if "name" in args:
        patch["name"] = args["name"]
    if "color" in args:
        patch["color"] = args["color"]
    if not patch:
        return {"error": "missing_argument", "message": "No fields to update"}
    return await call_user_api(ctx, "PATCH", f"/media/tags/{tag_id}", json_data=patch)


async def _handle_delete_tag(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    tag_id = args.get("id")
    if not tag_id:
        return {"error": "missing_argument", "message": "'id' is required"}
    return await call_user_api(ctx, "DELETE", f"/media/tags/{tag_id}")


async def _handle_tag_asset(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    asset_id = args.get("asset_id")
    tag_id = args.get("tag_id")
    if not asset_id:
        return {"error": "missing_argument", "message": "'asset_id' is required"}
    if not tag_id:
        return {"error": "missing_argument", "message": "'tag_id' is required"}
    return await call_user_api(
        ctx, "POST", "/media/assets/bulk/tag", json_data={"asset_ids": [asset_id], "tag_ids": [tag_id]}
    )


async def _handle_untag_asset(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.api_tools import call_user_api

    asset_id = args.get("asset_id")
    tag_id = args.get("tag_id")
    if not asset_id:
        return {"error": "missing_argument", "message": "'asset_id' is required"}
    if not tag_id:
        return {"error": "missing_argument", "message": "'tag_id' is required"}
    return await call_user_api(
        ctx, "POST", "/media/assets/bulk/tag", json_data={"asset_ids": [asset_id], "tag_ids": []}
    )


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

    num_clips = max(1, int(duration_seconds / 5))
    image_cost = 0.5 * num_clips
    video_cost = 2.0 * num_clips
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


async def _handle_generate_media(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Queue a quick media generation task. Returns a task_id for polling."""
    model_id = args.get("model_id")
    prompt = args.get("prompt")

    if not model_id:
        return {"error": "missing_argument", "message": "'model_id' is required"}
    if not prompt:
        return {"error": "missing_argument", "message": "'prompt' is required"}

    aspect_ratio = args.get("aspect_ratio", "1:1")
    duration = args.get("duration", 5)
    negative_prompt = args.get("negative_prompt")
    seed = args.get("seed")
    image_path = args.get("image_path")

    try:
        from app.workers.tasks import generate_quick_media

        task = generate_quick_media.delay(
            user_id=ctx.user_id,
            model_id=model_id,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            duration=duration,
            negative_prompt=negative_prompt,
            seed=seed,
            image_path=image_path,
        )
        return {
            "task_id": task.id,
            "status": "queued",
            "model_id": model_id,
            "prompt": prompt,
        }
    except ImportError:
        return {"error": "service_unavailable", "message": "Media generation worker not available"}
    except Exception as exc:
        return {"error": "generation_failed", "message": str(exc)}


async def _handle_list_projects(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """List projects for the current user."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}

    db: AsyncSession = ctx.db
    limit = args.get("limit", 50)
    result = await db.execute(
        select(Project)
        .where(Project.user_id == UUID(ctx.user_id))
        .order_by(Project.updated_at.desc())
        .limit(limit)
    )
    projects = []
    for project in result.scalars().all():
        projects.append({
            "id": str(project.id),
            "title": project.title,
            "description": project.description,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        })
    return {"projects": projects, "count": len(projects)}


async def _handle_create_project(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a new project for the current user."""
    if ctx.db is None:
        return {"error": "missing_db", "message": "Database session required"}

    title = args.get("title")
    if not title:
        return {"error": "missing_argument", "message": "'title' is required"}

    description = args.get("description")

    db: AsyncSession = ctx.db
    project = Project(
        user_id=UUID(ctx.user_id),
        title=title,
        description=description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return {
        "id": str(project.id),
        "title": project.title,
        "description": project.description,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


async def _handle_get_project(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get a single project by ID for the current user."""
    project_id = args.get("id")
    if not project_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    result = await call_user_api(ctx, "GET", f"/projects/{project_id}")
    return result


async def _handle_update_project(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Update a project (title and/or description) for the current user."""
    project_id = args.get("id")
    if not project_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    patch: dict[str, Any] = {}
    if "title" in args:
        patch["title"] = args["title"]
    if "description" in args:
        patch["description"] = args["description"]

    from app.chatbot.api_tools import call_user_api

    result = await call_user_api(ctx, "PATCH", f"/projects/{project_id}", json_data=patch)
    return result


async def _handle_delete_project(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Delete a project by ID for the current user. Fails if the project has associated jobs unless confirm=true."""
    project_id = args.get("id")
    if not project_id:
        return {"error": "missing_argument", "message": "'id' is required"}

    from app.chatbot.api_tools import call_user_api

    confirm = args.get("confirm", False)

    if not confirm:
        result = await call_user_api(ctx, "GET", f"/projects/{project_id}")
        if "error" in result:
            return result

        from sqlalchemy import func, select

        db: AsyncSession = ctx.db
        job_count = await db.execute(select(func.count()).where(Job.project_id == UUID(project_id)))
        if job_count.scalar() > 0:
            return {
                "error": "project_has_jobs",
                "message": "Project has associated jobs. Pass confirm=true to delete anyway.",
            }

    result = await call_user_api(ctx, "DELETE", f"/projects/{project_id}")
    return result


async def _handle_get_chat_token_usage(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get token usage aggregated by model or date range for the current user."""
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {}
    if "range" in args:
        params["range"] = args["range"]
    if "group_by" in args:
        params["group_by"] = args["group_by"]
    if "from_date" in args:
        params["from_date"] = args["from_date"]
    if "to_date" in args:
        params["to_date"] = args["to_date"]

    return await call_user_api(ctx, "GET", "/token-usage", params=params)


async def _handle_get_dashboard_token_usage(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get token usage aggregated by date bucket from the dashboard."""
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {}
    if "range" in args:
        params["range"] = args["range"]
    if "group_by" in args:
        params["group_by"] = args["group_by"]

    return await call_user_api(ctx, "GET", "/dashboard/token-usage", params=params)


async def _handle_get_dashboard_cost(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Get estimated cost aggregated by date bucket from the dashboard."""
    from app.chatbot.api_tools import call_user_api

    params: dict[str, Any] = {}
    if "range" in args:
        params["range"] = args["range"]
    if "group_by" in args:
        params["group_by"] = args["group_by"]

    return await call_user_api(ctx, "GET", "/dashboard/cost", params=params)


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
                    "reference_image_url": {"type": "string", "description": "URL of the user's attached image. When the user mentions an attached image, pass its URL here."},
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
            name="start_job",
            description="Start a pending job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                },
                "required": ["job_id"],
            },
            handler=_handle_start_job,
        )
    )

    registry.register(
        ToolDefinition(
            name="retry_job",
            description="Retry a failed or completed job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                },
                "required": ["job_id"],
            },
            handler=_handle_retry_job,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_job",
            description="Delete a job by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                },
                "required": ["job_id"],
            },
            handler=_handle_delete_job,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_job",
            description="Update a job's input_data.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                    "input_data": {"type": "object", "description": "Partial input data to merge"},
                },
                "required": ["job_id"],
            },
            handler=_handle_update_job,
        )
    )

    registry.register(
        ToolDefinition(
            name="download_job",
            description="Return a download URL for a completed job's output video.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                },
                "required": ["job_id"],
            },
            handler=_handle_download_job,
        )
    )

    registry.register(
        ToolDefinition(
            name="batch_create_jobs",
            description="Create multiple jobs in a batch.",
            input_schema={
                "type": "object",
                "properties": {
                    "template_id": {"type": "string", "description": "Template ID (UUID)"},
                    "jobs": {"type": "array", "description": "List of job input data objects"},
                    "project_id": {"type": "string", "description": "Optional project ID"},
                    "auto_start": {"type": "boolean", "description": "Auto-start jobs after creation", "default": True},
                    "provider_preference": {"type": "string", "description": "Provider preference", "default": "auto"},
                    "model_preference": {"type": "string", "description": "Optional model preference"},
                },
                "required": ["template_id", "jobs"],
            },
            handler=_handle_batch_create_jobs,
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

    registry.register(
        ToolDefinition(
            name="generate_media",
            description="Generate an image or video using AI. Provide a prompt, model, and optional settings.",
            input_schema={
                "type": "object",
                "properties": {
                    "model_id": {"type": "string", "description": "Model to use for generation"},
                    "prompt": {"type": "string", "description": "Text description of what to generate"},
                    "aspect_ratio": {"type": "string", "description": "e.g. 1:1, 16:9", "default": "1:1"},
                    "duration": {"type": "integer", "description": "Video duration in seconds", "default": 5},
                },
                "required": ["model_id", "prompt"],
            },
            handler=_handle_generate_media,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_projects",
            description="List projects for the current user, with optional limit.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum number of projects to return", "default": 50},
                },
            },
            handler=_handle_list_projects,
        )
    )

    registry.register(
        ToolDefinition(
            name="create_project",
            description="Create a new project with a title and optional description.",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Project title"},
                    "description": {"type": "string", "description": "Optional project description"},
                },
                "required": ["title"],
            },
            handler=_handle_create_project,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_project",
            description="Get a single project by ID for the current user.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Project ID (UUID)"},
                },
                "required": ["id"],
            },
            handler=_handle_get_project,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_project",
            description="Update a project (title and/or description) for the current user.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Project ID (UUID)"},
                    "title": {"type": "string", "description": "New project title"},
                    "description": {"type": "string", "description": "New project description"},
                },
                "required": ["id"],
            },
            handler=_handle_update_project,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_project",
            description="Delete a project by ID for the current user. Fails if the project has associated jobs unless confirm=true.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Project ID (UUID)"},
                    "confirm": {"type": "boolean", "description": "Set to true to delete a project that has associated jobs", "default": False},
                },
                "required": ["id"],
            },
            handler=_handle_delete_project,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_chat_token_usage",
            description="Get token usage aggregated by model or date range for the current user.",
            input_schema={
                "type": "object",
                "properties": {
                    "range": {"type": "string", "description": "Time range: 7d, 30d, 90d, or all"},
                    "group_by": {"type": "string", "description": "Group by: model or date"},
                    "from_date": {"type": "string", "description": "Start date in ISO format"},
                    "to_date": {"type": "string", "description": "End date in ISO format"},
                },
            },
            handler=_handle_get_chat_token_usage,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_dashboard_token_usage",
            description="Get token usage aggregated by date bucket from the dashboard.",
            input_schema={
                "type": "object",
                "properties": {
                    "range": {"type": "string", "description": "Time range: 7d, 30d, 90d, or all"},
                    "group_by": {"type": "string", "description": "Group by: hour, day, or month"},
                },
            },
            handler=_handle_get_dashboard_token_usage,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_dashboard_cost",
            description="Get estimated cost aggregated by date bucket from the dashboard.",
            input_schema={
                "type": "object",
                "properties": {
                    "range": {"type": "string", "description": "Time range: 7d, 30d, 90d, or all"},
                    "group_by": {"type": "string", "description": "Group by: hour, day, or month"},
                },
            },
            handler=_handle_get_dashboard_cost,
        )
    )

    # Templates
    registry.register(
        ToolDefinition(
            name="get_template",
            description="Get a single template by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Template ID (UUID)"},
                },
                "required": ["id"],
            },
            handler=_handle_get_template,
        )
    )

    registry.register(
        ToolDefinition(
            name="create_template",
            description="Create a new template.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Template name"},
                    "description": {"type": "string", "description": "Optional description"},
                    "config": {"type": "object", "description": "Template configuration object"},
                },
                "required": ["name", "config"],
            },
            handler=_handle_create_template,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_template",
            description="Update an existing template.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Template ID (UUID)"},
                    "name": {"type": "string", "description": "New template name"},
                    "description": {"type": "string", "description": "New description"},
                    "config": {"type": "object", "description": "New configuration object"},
                },
                "required": ["id"],
            },
            handler=_handle_update_template,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_template",
            description="Delete a template by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Template ID (UUID)"},
                },
                "required": ["id"],
            },
            handler=_handle_delete_template,
        )
    )

    # Styles
    registry.register(
        ToolDefinition(
            name="get_style",
            description="Get a single style by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Style ID (UUID)"},
                },
                "required": ["id"],
            },
            handler=_handle_get_style,
        )
    )

    registry.register(
        ToolDefinition(
            name="create_style",
            description="Create a new visual style.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Style name"},
                    "category": {"type": "string", "description": "Optional category"},
                    "params": {"type": "object", "description": "Style parameters"},
                },
                "required": ["name"],
            },
            handler=_handle_create_style,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_style",
            description="Update an existing style.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Style ID (UUID)"},
                    "name": {"type": "string", "description": "New style name"},
                    "category": {"type": "string", "description": "New category"},
                    "params": {"type": "object", "description": "New parameters"},
                },
                "required": ["id"],
            },
            handler=_handle_update_style,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_style",
            description="Delete a style by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Style ID (UUID)"},
                },
                "required": ["id"],
            },
            handler=_handle_delete_style,
        )
    )

    # Avatars
    registry.register(
        ToolDefinition(
            name="list_avatars",
            description="List avatars for the current user.",
            input_schema={
                "type": "object",
                "properties": {
                    "skip": {"type": "integer", "description": "Number of items to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of avatars to return", "default": 50},
                },
            },
            handler=_handle_list_avatars,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_avatar",
            description="Get a single avatar by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Avatar ID (UUID)"},
                },
                "required": ["id"],
            },
            handler=_handle_get_avatar,
        )
    )

    registry.register(
        ToolDefinition(
            name="create_avatar",
            description="Create a new avatar.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Avatar name"},
                    "gender": {"type": "string", "description": "Gender: Male, Female, Non-binary, or Other"},
                    "bio": {"type": "string", "description": "Optional bio"},
                    "consistency_strategy": {"type": "string", "description": "ip_adapter, face_swap, lora, or prompt_only", "default": "ip_adapter"},
                },
                "required": ["name"],
            },
            handler=_handle_create_avatar,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_avatar",
            description="Update an existing avatar.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Avatar ID (UUID)"},
                    "name": {"type": "string", "description": "New name"},
                    "gender": {"type": "string", "description": "New gender"},
                    "bio": {"type": "string", "description": "New bio"},
                    "consistency_strategy": {"type": "string", "description": "New strategy"},
                    "primary_image_id": {"type": "string", "description": "Primary image ID"},
                },
                "required": ["id"],
            },
            handler=_handle_update_avatar,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_avatar",
            description="Delete an avatar by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Avatar ID (UUID)"},
                },
                "required": ["id"],
            },
            handler=_handle_delete_avatar,
        )
    )

    # Audio
    registry.register(
        ToolDefinition(
            name="get_audio_status",
            description="Check whether the AudioCraft/MusicGen service is available.",
            input_schema={"type": "object", "properties": {}},
            handler=_handle_get_audio_status,
        )
    )

    registry.register(
        ToolDefinition(
            name="generate_music",
            description="Generate background music using AudioCraft/MusicGen.",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Music description prompt"},
                    "duration": {"type": "number", "description": "Duration in seconds (1-120)", "default": 15.0},
                    "output_format": {"type": "string", "description": "wav or mp3", "default": "mp3"},
                },
                "required": ["prompt"],
            },
            handler=_handle_generate_music,
        )
    )

    # Uploads (URL-only)
    registry.register(
        ToolDefinition(
            name="upload_image_url",
            description="Upload an image from a URL. Returns the file URL only.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Image URL or storage path"},
                },
                "required": ["url"],
            },
            handler=_handle_upload_image_url,
        )
    )

    registry.register(
        ToolDefinition(
            name="upload_video_url",
            description="Upload a video from a URL. Returns the file URL only.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Video URL or storage path"},
                },
                "required": ["url"],
            },
            handler=_handle_upload_video_url,
        )
    )

    registry.register(
        ToolDefinition(
            name="upload_audio_url",
            description="Upload an audio file from a URL. Returns the file URL only.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Audio URL or storage path"},
                },
                "required": ["url"],
            },
            handler=_handle_upload_audio_url,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_folders",
            description="List media folders for the current user.",
            input_schema={
                "type": "object",
                "properties": {
                    "parent_id": {"type": "string", "description": "Optional parent folder ID"},
                },
            },
            handler=_handle_list_folders,
        )
    )

    registry.register(
        ToolDefinition(
            name="create_folder",
            description="Create a new media folder.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Folder name"},
                    "parent_id": {"type": "string", "description": "Optional parent folder ID"},
                },
                "required": ["name"],
            },
            handler=_handle_create_folder,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_folder",
            description="Update a media folder (rename or move).",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Folder ID"},
                    "name": {"type": "string", "description": "New folder name"},
                    "parent_id": {"type": "string", "description": "New parent folder ID"},
                },
                "required": ["id"],
            },
            handler=_handle_update_folder,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_folder",
            description="Delete a media folder by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Folder ID"},
                },
                "required": ["id"],
            },
            handler=_handle_delete_folder,
        )
    )

    registry.register(
        ToolDefinition(
            name="folder_tree",
            description="Get the full media folder tree for the current user.",
            input_schema={"type": "object", "properties": {}},
            handler=_handle_folder_tree,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_assets",
            description="List media assets with optional filtering and pagination.",
            input_schema={
                "type": "object",
                "properties": {
                    "folder_id": {"type": "string", "description": "Filter by folder ID"},
                    "file_type": {"type": "string", "description": "Filter by file type (image, video, audio, markdown)"},
                    "search": {"type": "string", "description": "Search by name"},
                    "tag_ids": {"type": "array", "items": {"type": "string"}, "description": "Filter by tag IDs"},
                    "limit": {"type": "integer", "description": "Maximum items to return", "default": 20},
                    "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
                },
            },
            handler=_handle_list_assets,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_asset",
            description="Get a single media asset by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Asset ID"},
                },
                "required": ["id"],
            },
            handler=_handle_get_asset,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_asset",
            description="Update a media asset (rename, move, or change tags).",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Asset ID"},
                    "name": {"type": "string", "description": "New asset name"},
                    "folder_id": {"type": "string", "description": "New folder ID"},
                    "project_id": {"type": "string", "description": "New project ID"},
                    "tag_ids": {"type": "array", "items": {"type": "string"}, "description": "Tag IDs to set"},
                },
                "required": ["id"],
            },
            handler=_handle_update_asset,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_asset",
            description="Delete a media asset by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Asset ID"},
                },
                "required": ["id"],
            },
            handler=_handle_delete_asset,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_tags",
            description="List all media tags for the current user.",
            input_schema={"type": "object", "properties": {}},
            handler=_handle_list_tags,
        )
    )

    registry.register(
        ToolDefinition(
            name="create_tag",
            description="Create a new media tag.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tag name"},
                    "color": {"type": "string", "description": "Hex color (e.g. ff0000)"},
                },
                "required": ["name"],
            },
            handler=_handle_create_tag,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_tag",
            description="Update a media tag (rename or change color).",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Tag ID"},
                    "name": {"type": "string", "description": "New tag name"},
                    "color": {"type": "string", "description": "New hex color"},
                },
                "required": ["id"],
            },
            handler=_handle_update_tag,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_tag",
            description="Delete a media tag by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Tag ID"},
                },
                "required": ["id"],
            },
            handler=_handle_delete_tag,
        )
    )

    registry.register(
        ToolDefinition(
            name="tag_asset",
            description="Add a tag to a media asset.",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "Asset ID"},
                    "tag_id": {"type": "string", "description": "Tag ID"},
                },
                "required": ["asset_id", "tag_id"],
            },
            handler=_handle_tag_asset,
        )
    )

    registry.register(
        ToolDefinition(
            name="untag_asset",
            description="Remove a tag from a media asset.",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "Asset ID"},
                    "tag_id": {"type": "string", "description": "Tag ID"},
                },
                "required": ["asset_id", "tag_id"],
            },
            handler=_handle_untag_asset,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_audio_metadata",
            description="Get audio file duration and path for a job.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_get_audio_metadata,
        )
    )

    registry.register(
        ToolDefinition(
            name="extract_lyrics",
            description="Extract lyrics from a job's audio file.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_extract_lyrics,
        )
    )

    registry.register(
        ToolDefinition(
            name="set_manual_lyrics",
            description="Set lyrics manually for a job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "lyrics": {"type": "string", "description": "Full lyrics text"},
                    "duration": {"type": "number", "description": "Audio duration in seconds"},
                },
                "required": ["job_id", "lyrics", "duration"],
            },
            handler=_handle_set_manual_lyrics,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_lyrics",
            description="Update lyrics for a job and optionally replan scenes.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "lyrics": {"type": "string", "description": "Full lyrics text"},
                    "duration": {"type": "number", "description": "Audio duration in seconds"},
                    "replan": {"type": "boolean", "description": "Replan scenes after update", "default": False},
                    "style": {"type": "string", "description": "Visual style", "default": "realistic"},
                },
                "required": ["job_id", "lyrics", "duration"],
            },
            handler=_handle_update_lyrics,
        )
    )

    registry.register(
        ToolDefinition(
            name="plan_scenes",
            description="Plan scenes for a job from lyrics data.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "lyrics_data": {"type": "object", "description": "Parsed lyrics data"},
                    "duration": {"type": "number", "description": "Audio duration in seconds"},
                    "style": {"type": "string", "description": "Visual style", "default": "realistic"},
                },
                "required": ["job_id", "duration"],
            },
            handler=_handle_plan_scenes,
        )
    )

    registry.register(
        ToolDefinition(
            name="list_scenes",
            description="List all scenes for a job.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_list_scenes,
        )
    )

    registry.register(
        ToolDefinition(
            name="add_scene",
            description="Add a blank scene to a job.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_add_scene,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_scene",
            description="Update a scene's fields.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "scene_id": {"type": "string", "description": "Scene UUID"},
                    "start_time": {"type": "number"},
                    "end_time": {"type": "number"},
                    "lyrics_segment": {"type": "string"},
                    "visual_description": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "mood": {"type": "string"},
                    "camera_movement": {"type": "string"},
                    "reference_image_path": {"type": "string"},
                },
                "required": ["job_id", "scene_id"],
            },
            handler=_handle_update_scene,
        )
    )

    registry.register(
        ToolDefinition(
            name="delete_scene",
            description="Delete a scene from a job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "scene_id": {"type": "string", "description": "Scene UUID"},
                },
                "required": ["job_id", "scene_id"],
            },
            handler=_handle_delete_scene,
        )
    )

    registry.register(
        ToolDefinition(
            name="reorder_scenes",
            description="Reorder scenes for a job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "order": {"type": "array", "items": {"type": "string"}, "description": "Ordered list of scene UUIDs"},
                },
                "required": ["job_id", "order"],
            },
            handler=_handle_reorder_scenes,
        )
    )

    registry.register(
        ToolDefinition(
            name="set_job_stage",
            description="Set the processing stage of a job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "stage": {"type": "string", "description": "Stage: planning, planned, generating_images, images_ready, generating_videos, videos_ready, rendering, completed"},
                },
                "required": ["job_id", "stage"],
            },
            handler=_handle_set_job_stage,
        )
    )

    registry.register(
        ToolDefinition(
            name="regenerate_prompts",
            description="Regenerate image prompts for all scenes in a job.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_regenerate_prompts,
        )
    )

    registry.register(
        ToolDefinition(
            name="generate_scene_image",
            description="Queue image generation for a single scene.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "scene_id": {"type": "string", "description": "Scene UUID"},
                },
                "required": ["job_id", "scene_id"],
            },
            handler=_handle_generate_scene_image,
        )
    )

    registry.register(
        ToolDefinition(
            name="generate_scene_video",
            description="Queue video generation for a single scene.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "scene_id": {"type": "string", "description": "Scene UUID"},
                },
                "required": ["job_id", "scene_id"],
            },
            handler=_handle_generate_scene_video,
        )
    )

    registry.register(
        ToolDefinition(
            name="regenerate_all_scenes",
            description="Regenerate all scenes for a job (re-plan + generate images + videos).",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_regenerate_all_scenes,
        )
    )

    registry.register(
        ToolDefinition(
            name="generate_all_images",
            description="Queue image generation for all scenes in a job.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_generate_all_images,
        )
    )

    registry.register(
        ToolDefinition(
            name="generate_all_videos",
            description="Queue video generation for all scenes in a job.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_generate_all_videos,
        )
    )

    registry.register(
        ToolDefinition(
            name="export_job",
            description="Export a completed job to a final video.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job UUID"},
                    "audio_file": {"type": "string"},
                    "background_music": {"type": "string"},
                    "audio_volume": {"type": "number", "default": 1.0},
                    "background_music_volume": {"type": "number", "default": 0.3},
                    "transition_type": {"type": "string", "default": "cut"},
                },
                "required": ["job_id"],
            },
            handler=_handle_export_job,
        )
    )

    registry.register(
        ToolDefinition(
            name="get_export_options",
            description="Get export options and readiness for a job.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job UUID"}},
                "required": ["job_id"],
            },
            handler=_handle_get_export_options,
        )
    )

    # User settings
    registry.register(
        ToolDefinition(
            name="get_user_settings",
            description="Get the current user's settings.",
            input_schema={"type": "object", "properties": {}},
            handler=_handle_get_user_settings,
        )
    )

    registry.register(
        ToolDefinition(
            name="update_user_settings",
            description="Update the current user's settings.",
            input_schema={
                "type": "object",
                "properties": {
                    "default_style_id": {"type": "string", "description": "Default style UUID"},
                    "storage_backend": {"type": "string", "description": "Storage backend name"},
                    "storage_config": {"type": "object", "description": "Storage configuration"},
                    "preferences": {"type": "object", "description": "User preferences"},
                },
            },
            handler=_handle_update_user_settings,
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


_LYRICS_TRUNCATE_AT = 8 * 1024


def _maybe_truncate_lyrics(payload: dict[str, Any]) -> dict[str, Any]:
    lyrics = payload.get("lyrics")
    if isinstance(lyrics, str) and len(lyrics.encode("utf-8")) > _LYRICS_TRUNCATE_AT:
        payload["lyrics"] = lyrics[:_LYRICS_TRUNCATE_AT] + "\n...[truncated]"
    elif isinstance(lyrics, dict):
        full_text = lyrics.get("full_text", "")
        if len(full_text.encode("utf-8")) > _LYRICS_TRUNCATE_AT:
            lyrics["full_text"] = full_text[:_LYRICS_TRUNCATE_AT] + "\n...[truncated]"
        payload["lyrics"] = lyrics
    return payload


async def _handle_get_audio_metadata(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", f"/jobs/{job_id}/audio-metadata")


async def _handle_extract_lyrics(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    result = await call_user_api(
        ctx, "POST", f"/jobs/{job_id}/lyrics/extract", json_data={"audio_file_path": ""}
    )
    return _maybe_truncate_lyrics(result)


async def _handle_set_manual_lyrics(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    lyrics = args.get("lyrics")
    duration = args.get("duration")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if lyrics is None:
        return {"error": "missing_argument", "message": "'lyrics' is required"}
    if duration is None:
        return {"error": "missing_argument", "message": "'duration' is required"}

    from app.chatbot.api_tools import call_user_api

    result = await call_user_api(
        ctx,
        "POST",
        f"/jobs/{job_id}/lyrics/manual",
        json_data={"lyrics_text": lyrics, "duration": duration},
    )
    return _maybe_truncate_lyrics(result)


async def _handle_update_lyrics(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    lyrics = args.get("lyrics")
    duration = args.get("duration")
    replan = args.get("replan", False)
    style = args.get("style", "realistic")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if lyrics is None:
        return {"error": "missing_argument", "message": "'lyrics' is required"}
    if duration is None:
        return {"error": "missing_argument", "message": "'duration' is required"}

    from app.chatbot.api_tools import call_user_api

    result = await call_user_api(
        ctx,
        "PUT",
        f"/jobs/{job_id}/lyrics",
        json_data={"lyrics_text": lyrics, "duration": duration, "replan": replan, "style": style},
    )
    return _maybe_truncate_lyrics(result)


async def _handle_plan_scenes(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    lyrics_data = args.get("lyrics_data", {})
    duration = args.get("duration")
    style = args.get("style", "realistic")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if duration is None:
        return {"error": "missing_argument", "message": "'duration' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(
        ctx,
        "POST",
        f"/jobs/{job_id}/scenes/plan",
        json_data={"lyrics_data": lyrics_data, "duration": duration, "style": style},
    )


async def _handle_list_scenes(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", f"/jobs/{job_id}/scenes")


async def _handle_add_scene(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", f"/jobs/{job_id}/scenes")


async def _handle_update_scene(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    scene_id = args.get("scene_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if not scene_id:
        return {"error": "missing_argument", "message": "'scene_id' is required"}

    patch: dict[str, Any] = {}
    for field in (
        "start_time",
        "end_time",
        "lyrics_segment",
        "visual_description",
        "image_prompt",
        "mood",
        "camera_movement",
        "reference_image_path",
    ):
        if field in args:
            patch[field] = args[field]

    if not patch:
        return {"error": "missing_argument", "message": "No fields to update"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(
        ctx, "PATCH", f"/jobs/{job_id}/scenes/{scene_id}", json_data=patch
    )


async def _handle_delete_scene(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    scene_id = args.get("scene_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if not scene_id:
        return {"error": "missing_argument", "message": "'scene_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "DELETE", f"/jobs/{job_id}/scenes/{scene_id}")


async def _handle_reorder_scenes(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    order = args.get("order")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if not order:
        return {"error": "missing_argument", "message": "'order' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(
        ctx, "POST", f"/jobs/{job_id}/scenes/reorder", json_data=order
    )


async def _handle_set_job_stage(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    stage = args.get("stage")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if not stage:
        return {"error": "missing_argument", "message": "'stage' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(
        ctx, "PATCH", f"/jobs/{job_id}/stage", json_data={"stage": stage}
    )


async def _handle_regenerate_prompts(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", f"/jobs/{job_id}/scenes/regenerate-prompts")


async def _handle_generate_scene_image(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    scene_id = args.get("scene_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if not scene_id:
        return {"error": "missing_argument", "message": "'scene_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(
        ctx, "POST", f"/jobs/{job_id}/scenes/generate-image/{scene_id}"
    )


async def _handle_generate_scene_video(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    scene_id = args.get("scene_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}
    if not scene_id:
        return {"error": "missing_argument", "message": "'scene_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(
        ctx, "POST", f"/jobs/{job_id}/scenes/generate-video/{scene_id}"
    )


async def _handle_regenerate_all_scenes(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", f"/jobs/{job_id}/scenes/regenerate-all")


async def _handle_generate_all_images(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", f"/jobs/{job_id}/scenes/generate-all-images")


async def _handle_generate_all_videos(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "POST", f"/jobs/{job_id}/scenes/generate-all-videos")


async def _handle_export_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    options: dict[str, Any] = {}
    for field in (
        "audio_file",
        "background_music",
        "audio_volume",
        "background_music_volume",
        "transition_type",
    ):
        if field in args:
            options[field] = args[field]

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(
        ctx, "POST", f"/jobs/{job_id}/export", json_data=options
    )


async def _handle_get_export_options(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "missing_argument", "message": "'job_id' is required"}

    from app.chatbot.api_tools import call_user_api

    return await call_user_api(ctx, "GET", f"/jobs/{job_id}/export-options")
