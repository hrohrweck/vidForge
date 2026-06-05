"""Capture and persist error events for the notification system.

This module provides the core error capture functionality for VidForge's
notification system. It creates ErrorEvent records in the database and
optionally logs them via Python's logging module.

The capture is intentionally simple: single attempt, no retry. If the
database write fails, the error is lost — that's acceptable for a
notification system (the original error is still in the job status).

Separation of concerns: this module does NOT push to WebSocket. That's
the notification_dispatcher's job, called separately after the DB write.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import ErrorEvent, ErrorOrigin, ErrorSeverity

logger = logging.getLogger(__name__)

# Limits to prevent log bloat and database bloat
MAX_MESSAGE_LENGTH = 2000
MAX_DETAIL_VALUE_LENGTH = 10_000  # 10KB per value


def _sanitize_message(message: str) -> str:
    """Truncate message to max length to prevent database bloat."""
    if len(message) > MAX_MESSAGE_LENGTH:
        return message[:MAX_MESSAGE_LENGTH] + "..."
    return message


def _sanitize_details(details: dict | None) -> dict | None:
    """Sanitize details dict: truncate long strings, drop non-serializable objects.

    Returns a new dict with sanitized values, or None if input is None.
    """
    if details is None:
        return None

    sanitized = {}
    for key, value in details.items():
        # Truncate long strings
        if isinstance(value, str) and len(value) > MAX_DETAIL_VALUE_LENGTH:
            sanitized[key] = value[:MAX_DETAIL_VALUE_LENGTH] + "... (truncated)"
        # Keep primitives and None
        elif isinstance(value, (str, int, float, bool, type(None))):
            sanitized[key] = value
        # Convert lists/dicts recursively (shallow for now)
        elif isinstance(value, (list, dict)):
            try:
                # Try to serialize to catch non-serializable objects
                import json

                json.dumps(value)
                sanitized[key] = value
            except (TypeError, ValueError):
                # Drop non-serializable objects
                logger.debug("Dropping non-serializable detail key: %s", key)
        else:
            # Drop non-serializable objects
            logger.debug("Dropping non-serializable detail key: %s (type: %s)", key, type(value))

    return sanitized


async def log_error_event(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    severity: ErrorSeverity,
    origin: ErrorOrigin,
    message: str,
    details: dict | None = None,
    source_id: UUID | None = None,
    source_type: str | None = None,
) -> ErrorEvent:
    """Create and persist an error event in the database.

    This is the core function for capturing errors. It creates an ErrorEvent
    record, commits it to the database, and returns the persisted instance.

    Args:
        db: Async database session
        user_id: ID of the affected user (None for system errors)
        severity: Error severity level (info, warning, error, critical)
        origin: Subsystem where the error occurred
        message: Human-readable error message (max 2000 chars)
        details: Optional dict with technical details (stack traces, payloads, etc.)
        source_id: Optional ID of the related entity (e.g., Job ID)
        source_type: Optional type of the related entity (e.g., "job")

    Returns:
        The persisted ErrorEvent instance with ID and timestamps populated

    Raises:
        SQLAlchemyError: If the database write fails (no retry)

    Example:
        >>> event = await log_error_event(
        ...     db,
        ...     user_id=job.user_id,
        ...     severity=ErrorSeverity.ERROR,
        ...     origin=ErrorOrigin.MEDIA_GENERATION,
        ...     message="Image generation failed",
        ...     details={"provider": "comfyui", "model": "flux1-schnell"},
        ...     source_id=job.id,
        ...     source_type="job",
        ... )
    """
    # Sanitize inputs
    sanitized_message = _sanitize_message(message)
    sanitized_details = _sanitize_details(details)

    # Create the error event
    event = ErrorEvent(
        user_id=user_id,
        severity=severity,
        origin=origin,
        message=sanitized_message,
        details=sanitized_details,
        source_id=source_id,
        source_type=source_type,
    )

    # Persist to database
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # Also log via Python logging for stdout/file logs
    log_level = {
        ErrorSeverity.INFO: logging.INFO,
        ErrorSeverity.WARNING: logging.WARNING,
        ErrorSeverity.ERROR: logging.ERROR,
        ErrorSeverity.CRITICAL: logging.CRITICAL,
    }.get(severity, logging.ERROR)

    logger.log(
        log_level,
        "[%s] %s: %s (user=%s, source=%s:%s)",
        origin.value,
        severity.value,
        sanitized_message,
        user_id,
        source_type,
        source_id,
    )

    return event


async def log_user_error(
    db: AsyncSession,
    user_id: UUID,
    severity: ErrorSeverity,
    origin: ErrorOrigin,
    message: str,
    **kwargs,
) -> ErrorEvent:
    """Convenience helper for logging user-facing errors.

    Asserts that user_id is provided (user errors must have a user).

    Args:
        db: Async database session
        user_id: ID of the affected user (required)
        severity: Error severity level
        origin: Subsystem where the error occurred
        message: Human-readable error message
        **kwargs: Additional arguments passed to log_error_event

    Returns:
        The persisted ErrorEvent instance

    Raises:
        AssertionError: If user_id is None
        SQLAlchemyError: If the database write fails
    """
    assert user_id is not None, "log_user_error requires a user_id"
    return await log_error_event(
        db,
        user_id=user_id,
        severity=severity,
        origin=origin,
        message=message,
        **kwargs,
    )


async def log_system_error(
    db: AsyncSession,
    severity: ErrorSeverity,
    origin: ErrorOrigin,
    message: str,
    **kwargs,
) -> ErrorEvent:
    """Convenience helper for logging system errors (no user context).

    System errors have user_id=None and are only visible to admins.

    Args:
        db: Async database session
        severity: Error severity level
        origin: Subsystem where the error occurred
        message: Human-readable error message
        **kwargs: Additional arguments passed to log_error_event

    Returns:
        The persisted ErrorEvent instance

    Raises:
        SQLAlchemyError: If the database write fails
    """
    return await log_error_event(
        db,
        user_id=None,
        severity=severity,
        origin=origin,
        message=message,
        **kwargs,
    )
