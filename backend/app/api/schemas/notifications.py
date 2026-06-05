"""Pydantic schemas for the notification system.

Schemas use the ``to_camel`` alias generator so the API returns ``camelCase``
fields (matching the frontend convention) while keeping ``snake_case``
attributes on the Python side.  Response models also set
``from_attributes=True`` so they can be built directly from SQLAlchemy ORM
instances.

The user-facing ``ErrorEventResponse`` deliberately omits the ``details``
blob — those are exposed to admins only via a separate endpoint.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.database import ErrorOrigin, ErrorSeverity

_NOTIFICATION_MODEL_CONFIG = ConfigDict(
    from_attributes=True,
    alias_generator=to_camel,
    populate_by_name=True,
)


class ErrorEventResponse(BaseModel):
    """User-facing representation of a single ``ErrorEvent`` row.

    Intentionally excludes ``details`` — technical context (stack traces,
    provider payloads, etc.) is admin-only and exposed via a separate schema
    on the admin endpoint.
    """

    model_config = _NOTIFICATION_MODEL_CONFIG

    id: UUID
    user_id: UUID | None = None
    severity: ErrorSeverity
    origin: ErrorOrigin
    message: str
    source_id: UUID | None = None
    source_type: str | None = None
    created_at: datetime
    read_at: datetime | None = None


class ErrorEventListResponse(BaseModel):
    """Paginated envelope returned by ``GET /api/notifications``."""

    model_config = _NOTIFICATION_MODEL_CONFIG

    items: list[ErrorEventResponse]
    total: int
    unread_count: int


class ErrorEventFilterParams(BaseModel):
    """Query-string filter parameters for listing error events."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    severity: list[ErrorSeverity] | None = None
    origin: list[ErrorOrigin] | None = None
    unread_only: bool = False
    limit: int = 50
    offset: int = 0


class MarkReadResponse(BaseModel):
    """Response from the mark-as-read endpoint(s)."""

    model_config = _NOTIFICATION_MODEL_CONFIG

    success: bool
