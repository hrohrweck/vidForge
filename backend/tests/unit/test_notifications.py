"""Unit tests for the notification system (error_capture module).

Tests the core error capture functionality:
- Message truncation to 2000 chars
- Details sanitization (non-serializable dropped)
- log_user_error creates event with correct fields
- log_system_error creates event with user_id=None

Uses SQLite in-memory database via conftest.py fixtures.
"""

import pytest
from uuid import uuid4

from app.database import ErrorEvent, ErrorOrigin, ErrorSeverity
from app.services.error_capture import (
    _sanitize_message,
    _sanitize_details,
    log_error_event,
    log_user_error,
    log_system_error,
)


# ── Sanitization Tests ─────────────────────────────────────────────────────


class TestSanitizeMessage:
    """Test message truncation logic."""

    def test_short_message_unchanged(self):
        """Messages under 2000 chars are not truncated."""
        message = "Short error message"
        result = _sanitize_message(message)
        assert result == message

    def test_exact_limit_unchanged(self):
        """Messages exactly at 2000 chars are not truncated."""
        message = "x" * 2000
        result = _sanitize_message(message)
        assert result == message
        assert len(result) == 2000

    def test_long_message_truncated(self):
        """Messages over 2000 chars are truncated with ellipsis."""
        message = "x" * 2500
        result = _sanitize_message(message)
        assert len(result) == 2003  # 2000 + "..."
        assert result.endswith("...")
        assert result.startswith("x" * 2000)

    def test_empty_message(self):
        """Empty messages are handled correctly."""
        result = _sanitize_message("")
        assert result == ""


class TestSanitizeDetails:
    """Test details dict sanitization."""

    def test_none_details_returns_none(self):
        """None input returns None."""
        result = _sanitize_details(None)
        assert result is None

    def test_empty_dict_returns_empty(self):
        """Empty dict returns empty dict."""
        result = _sanitize_details({})
        assert result == {}

    def test_primitives_preserved(self):
        """Primitive types (str, int, float, bool, None) are preserved."""
        details = {
            "string": "value",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }
        result = _sanitize_details(details)
        assert result == details

    def test_long_string_truncated(self):
        """Strings over 10000 chars are truncated."""
        details = {"long": "x" * 15000}
        result = _sanitize_details(details)
        assert len(result["long"]) < 15000
        assert result["long"].endswith("... (truncated)")

    def test_serializable_list_preserved(self):
        """Lists with serializable content are preserved."""
        details = {"list": [1, 2, 3, "four"]}
        result = _sanitize_details(details)
        assert result == details

    def test_serializable_dict_preserved(self):
        """Nested dicts with serializable content are preserved."""
        details = {"nested": {"key": "value", "num": 42}}
        result = _sanitize_details(details)
        assert result == details

    def test_non_serializable_dropped(self):
        """Non-serializable objects are dropped from details."""
        import datetime
        
        details = {
            "good": "value",
            "bad_datetime": datetime.datetime.now(),
            "bad_object": object(),
        }
        result = _sanitize_details(details)
        assert "good" in result
        assert "bad_datetime" not in result
        assert "bad_object" not in result

    def test_list_with_non_serializable_dropped(self):
        """Lists containing non-serializable objects are dropped."""
        details = {
            "good_list": [1, 2, 3],
            "bad_list": [1, 2, object()],
        }
        result = _sanitize_details(details)
        assert "good_list" in result
        assert "bad_list" not in result


# ── Error Event Creation Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_error_event_creates_record(db_session, regular_user):
    """log_error_event creates and persists an ErrorEvent record."""
    event = await log_error_event(
        db_session,
        user_id=regular_user.id,
        severity=ErrorSeverity.ERROR,
        origin=ErrorOrigin.MEDIA_GENERATION,
        message="Test error message",
        details={"provider": "test", "model": "test-model"},
        source_id=uuid4(),
        source_type="job",
    )

    assert event.id is not None
    assert event.user_id == regular_user.id
    assert event.severity == ErrorSeverity.ERROR
    assert event.origin == ErrorOrigin.MEDIA_GENERATION
    assert event.message == "Test error message"
    assert event.details == {"provider": "test", "model": "test-model"}
    assert event.source_type == "job"
    assert event.created_at is not None
    assert event.read_at is None


@pytest.mark.asyncio
async def test_log_error_event_truncates_long_message(db_session, regular_user):
    """log_error_event truncates messages over 2000 chars."""
    long_message = "x" * 3000
    event = await log_error_event(
        db_session,
        user_id=regular_user.id,
        severity=ErrorSeverity.WARNING,
        origin=ErrorOrigin.LLM,
        message=long_message,
    )

    assert len(event.message) == 2003  # 2000 + "..."
    assert event.message.endswith("...")


@pytest.mark.asyncio
async def test_log_error_event_sanitizes_details(db_session, regular_user):
    """log_error_event drops non-serializable details."""
    import datetime
    
    details = {
        "good": "value",
        "bad": datetime.datetime.now(),
    }
    event = await log_error_event(
        db_session,
        user_id=regular_user.id,
        severity=ErrorSeverity.INFO,
        origin=ErrorOrigin.SYSTEM,
        message="Test",
        details=details,
    )

    assert "good" in event.details
    assert "bad" not in event.details


@pytest.mark.asyncio
async def test_log_user_error_requires_user_id(db_session):
    """log_user_error asserts that user_id is provided."""
    with pytest.raises(AssertionError, match="log_user_error requires a user_id"):
        await log_user_error(
            db_session,
            user_id=None,
            severity=ErrorSeverity.ERROR,
            origin=ErrorOrigin.MEDIA_GENERATION,
            message="Should fail",
        )


@pytest.mark.asyncio
async def test_log_user_error_creates_event(db_session, regular_user):
    """log_user_error creates an event with the correct user_id."""
    event = await log_user_error(
        db_session,
        user_id=regular_user.id,
        severity=ErrorSeverity.ERROR,
        origin=ErrorOrigin.VIDEO_GENERATION,
        message="User-specific error",
        details={"step": "rendering"},
    )

    assert event.user_id == regular_user.id
    assert event.severity == ErrorSeverity.ERROR
    assert event.origin == ErrorOrigin.VIDEO_GENERATION
    assert event.message == "User-specific error"
    assert event.details == {"step": "rendering"}


@pytest.mark.asyncio
async def test_log_system_error_creates_event_with_null_user(db_session):
    """log_system_error creates an event with user_id=None."""
    event = await log_system_error(
        db_session,
        severity=ErrorSeverity.CRITICAL,
        origin=ErrorOrigin.SYSTEM,
        message="System-wide failure",
        details={"component": "database"},
    )

    assert event.user_id is None
    assert event.severity == ErrorSeverity.CRITICAL
    assert event.origin == ErrorOrigin.SYSTEM
    assert event.message == "System-wide failure"
    assert event.details == {"component": "database"}


@pytest.mark.asyncio
async def test_log_error_event_all_severity_levels(db_session, regular_user):
    """log_error_event works with all severity levels."""
    for severity in [ErrorSeverity.INFO, ErrorSeverity.WARNING, ErrorSeverity.ERROR, ErrorSeverity.CRITICAL]:
        event = await log_error_event(
            db_session,
            user_id=regular_user.id,
            severity=severity,
            origin=ErrorOrigin.SYSTEM,
            message=f"Test {severity.value}",
        )
        assert event.severity == severity


@pytest.mark.asyncio
async def test_log_error_event_all_origins(db_session, regular_user):
    """log_error_event works with all origin types."""
    for origin in [
        ErrorOrigin.MEDIA_GENERATION,
        ErrorOrigin.VIDEO_GENERATION,
        ErrorOrigin.AUDIO_GENERATION,
        ErrorOrigin.LLM,
        ErrorOrigin.STORAGE,
        ErrorOrigin.UPLOAD,
        ErrorOrigin.SYSTEM,
    ]:
        event = await log_error_event(
            db_session,
            user_id=regular_user.id,
            severity=ErrorSeverity.INFO,
            origin=origin,
            message=f"Test {origin.value}",
        )
        assert event.origin == origin


@pytest.mark.asyncio
async def test_log_error_event_without_details(db_session, regular_user):
    """log_error_event works when details is None."""
    event = await log_error_event(
        db_session,
        user_id=regular_user.id,
        severity=ErrorSeverity.INFO,
        origin=ErrorOrigin.SYSTEM,
        message="No details",
    )

    assert event.details is None


@pytest.mark.asyncio
async def test_log_error_event_without_source(db_session, regular_user):
    """log_error_event works when source_id and source_type are None."""
    event = await log_error_event(
        db_session,
        user_id=regular_user.id,
        severity=ErrorSeverity.INFO,
        origin=ErrorOrigin.SYSTEM,
        message="No source",
    )

    assert event.source_id is None
    assert event.source_type is None
