"""In-process ASGI helper for routing tool calls through the public API as the user."""

from typing import Any

import httpx
from httpx import ASGITransport

from app.api.auth import create_access_token
from app.chatbot.tools import ToolContext
from app.main import app

MAX_RESPONSE_BYTES = 8 * 1024  # 8 KB cap

# Hardcoded short-lived token TTL to avoid circular import
_SHORT_LIVED_MINUTES = 5


def _is_blocked_path(path: str, method: str) -> bool:
    """Return True if the path/method combo is blocked for non-admin users."""
    if path.startswith("/api/admin"):
        return True
    # Block all write methods on /api/providers
    if path.startswith("/api/providers") and method in ("POST", "PUT", "PATCH", "DELETE"):
        return True
    return False


async def call_user_api(
    ctx: ToolContext,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Call the FastAPI public API in-process, signing the request as ``ctx.user_id``.

    Blocks requests to admin endpoints and provider write operations.
    Caps JSON responses at 8 KB; larger payloads are returned as an error.
    4xx/5xx responses are serialised as ``{"error": "<status>", "message": "<body>"}``.
    """
    # FastAPI routers are mounted under /api; prepend if caller omitted it
    api_path = path if path.startswith("/api") else f"/api{path}"

    if _is_blocked_path(api_path, method):
        return {"error": "forbidden", "message": "Admin or provider write endpoints are not accessible via tools."}

    token = create_access_token(data={"sub": ctx.user_id})
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=httpx.Timeout(30.0),
    ) as client:
        response = await client.request(
            method=method,
            url=api_path,
            params=params,
            json=json_data,
            headers=headers,
        )

    if response.status_code >= 400:
        body = response.text
        try:
            body = response.json()
        except Exception:
            pass
        if isinstance(body, dict):
            msg = body.get("detail") or body.get("message") or str(body)
        else:
            msg = body or ""
        status_map = {404: "not_found", 403: "forbidden", 401: "unauthorized"}
        return {"error": status_map.get(response.status_code, str(response.status_code)), "message": msg}

    raw = response.content
    if len(raw) > MAX_RESPONSE_BYTES:
        return {
            "error": "payload_too_large",
            "message": f"Response exceeded 8 KB cap ({len(raw)} bytes).",
        }

    try:
        return response.json()
    except Exception:
        return {"error": "invalid_json", "message": "Response was not valid JSON."}
