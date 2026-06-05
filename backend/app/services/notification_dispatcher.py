"""Dispatch error-event notifications to users and admins via Redis pub/sub.

The dispatcher is intentionally decoupled from the database write path —
callers invoke :func:`dispatch_error_event` in a fire-and-forget fashion so
that a Redis outage never blocks error persistence.

Payload policy
--------------
* **User channel** (``notifications:user:{user_id}``): contains only the
  fields from :class:`~app.api.schemas.notifications.ErrorEventResponse`
  — ``details`` is deliberately excluded.
* **Admin channel** (``notifications:admin``): contains the full event
  including ``details`` (stack traces, provider payloads, etc.).
"""

from __future__ import annotations

import json
import logging

from app.database import ErrorEvent
from app.workers.context import ctx

logger = logging.getLogger(__name__)


def _base_payload(event: ErrorEvent) -> dict:
    """Build the payload fields shared by user and admin channels."""
    return {
        "type": "error_event",
        "id": str(event.id),
        "user_id": str(event.user_id),
        "severity": event.severity,
        "origin": event.origin,
        "message": event.message,
        "source_id": str(event.source_id) if event.source_id else None,
        "source_type": event.source_type,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "read_at": event.read_at.isoformat() if event.read_at else None,
    }


def _user_payload(event: ErrorEvent) -> dict:
    """User-facing payload — excludes ``details``."""
    return _base_payload(event)


def _admin_payload(event: ErrorEvent) -> dict:
    """Admin payload — includes ``details`` for debugging."""
    payload = _base_payload(event)
    payload["details"] = event.details
    return payload


async def dispatch_error_event(event: ErrorEvent) -> None:
    """Publish an error event to the user and admin Redis channels.

    This is fire-and-forget: any Redis failure is logged but never raised,
    so the caller's database write is never blocked.
    """
    try:
        user_channel = f"notifications:user:{event.user_id}"
        admin_channel = "notifications:admin"

        await ctx.redis.publish(user_channel, json.dumps(_user_payload(event)))
        await ctx.redis.publish(admin_channel, json.dumps(_admin_payload(event)))
    except Exception:
        logger.warning(
            "Failed to dispatch notification for error event %s",
            event.id,
            exc_info=True,
        )
