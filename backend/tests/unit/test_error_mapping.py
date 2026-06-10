"""Tests for error_mapping.classify_provider_error.

Table-driven: every (exception-pattern → user message, recoverable?) pair
from all four former duplicate sites.
"""

import pytest

from app.services.error_mapping import ClassifiedError, classify_provider_error
from app.services.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.services.video_processor import InvalidVideoOutputError


class TestTypedExceptions:
    def test_invalid_video_output(self):
        from app.services.video_processor import ValidationResult

        result = ValidationResult(
            valid=False, actual_frames=10, expected_frames=30, actual_duration=2.0
        )
        exc = InvalidVideoOutputError("/tmp/test.mp4", result)
        classified = classify_provider_error(exc)
        assert classified.category == "validation"
        assert "10 frames" in classified.message
        assert "expected 30" in classified.message
        assert not classified.recoverable

    def test_provider_overloaded(self):
        exc = ProviderOverloadedError("Service overloaded")
        classified = classify_provider_error(exc)
        assert classified.category == "overloaded"
        assert classified.message == "AI service is busy, please try again later"
        assert classified.recoverable

    def test_provider_rate_limit(self):
        exc = ProviderRateLimitError("Rate limited")
        classified = classify_provider_error(exc)
        assert classified.category == "rate_limit"
        assert classified.message == "Too many requests, please try again later"
        assert classified.recoverable

    def test_provider_connection(self):
        exc = ProviderConnectionError("Connection refused")
        classified = classify_provider_error(exc)
        assert classified.category == "connection"
        assert classified.message == "Connection failed, please check your network"
        assert classified.recoverable

    def test_provider_timeout(self):
        exc = ProviderTimeoutError("Timed out")
        classified = classify_provider_error(exc)
        assert classified.category == "timeout"
        assert classified.message == "Request timed out, please try again later"
        assert classified.recoverable

    def test_generic_provider_error(self):
        exc = ProviderError("Something went wrong")
        classified = classify_provider_error(exc)
        assert classified.category == "provider"
        assert "generation service error, please try again" in classified.message
        assert not classified.recoverable


class TestStringFallbackOverloaded:
    @pytest.mark.parametrize(
        "message",
        [
            "Engine overloaded",
            "Server at capacity",
            "Queue is full",
            "GPU capacity exceeded",
            "overloaded",
        ],
    )
    def test_overloaded_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "overloaded"
        assert classified.message == "AI service is busy, please try again later"
        assert classified.recoverable


class TestStringFallbackRateLimit:
    @pytest.mark.parametrize(
        "message",
        [
            "Rate limit exceeded",
            "429 Too Many Requests",
            "too many requests",
        ],
    )
    def test_rate_limit_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "rate_limit"
        assert classified.message == "Too many requests, please try again later"
        assert classified.recoverable


class TestStringFallbackConnection:
    @pytest.mark.parametrize(
        "message",
        [
            "Connection refused",
            "ConnectionError",
            "connection reset",
            "connectionerror",
        ],
    )
    def test_connection_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "connection"
        assert classified.message == "Connection failed, please check your network"
        assert classified.recoverable

    def test_builtin_connection_error(self):
        exc = ConnectionError("Network unreachable")
        classified = classify_provider_error(exc)
        assert classified.category == "connection"
        assert classified.message == "Connection failed, please check your network"
        assert classified.recoverable


class TestStringFallbackTimeout:
    @pytest.mark.parametrize(
        "message",
        [
            "Request timeout",
            "Operation timed out",
            "timeout",
            "timed out",
        ],
    )
    def test_timeout_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "timeout"
        assert classified.message == "Request timed out, please try again later"
        assert classified.recoverable

    def test_builtin_timeout_error(self):
        exc = TimeoutError("Took too long")
        classified = classify_provider_error(exc)
        assert classified.category == "timeout"
        assert classified.message == "Request timed out, please try again later"
        assert classified.recoverable


class TestStringFallbackNoData:
    @pytest.mark.parametrize(
        "message",
        [
            "generation returned no output data",
            "no data returned",
            "no output from model",
        ],
    )
    def test_no_data_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "no_data"
        assert "returned no data" in classified.message
        assert not classified.recoverable


class TestStringFallbackServerErrors:
    @pytest.mark.parametrize(
        "message",
        [
            "503 Service Unavailable",
            "502 Bad Gateway",
            "internal server error",
            "server error",
        ],
    )
    def test_server_error_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "server_error"
        assert classified.recoverable


class TestStringFallbackTemporary:
    @pytest.mark.parametrize(
        "message",
        [
            "temporary failure",
            "please retry",
            "try again later",
        ],
    )
    def test_temporary_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "temporary"
        assert classified.recoverable


class TestStringFallbackNoOutputMedia:
    @pytest.mark.parametrize(
        "message",
        [
            "returned no image",
            "returned no video",
        ],
    )
    def test_no_output_media_variants(self, message: str):
        exc = RuntimeError(message)
        classified = classify_provider_error(exc)
        assert classified.category == "no_data"
        assert not classified.recoverable


class TestGenericFallback:
    def test_unknown_error(self):
        exc = RuntimeError("Something completely unexpected")
        classified = classify_provider_error(exc)
        assert classified.category == "unknown"
        assert classified.message == "An error occurred, please try again"
        assert not classified.recoverable

    def test_empty_message(self):
        exc = RuntimeError("")
        classified = classify_provider_error(exc)
        assert classified.category == "unknown"
        assert classified.message == "An error occurred, please try again"
        assert not classified.recoverable
