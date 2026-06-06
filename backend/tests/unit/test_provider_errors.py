"""Tests for ProviderBase.classify_error default implementation.

The default ``classify_error`` maps arbitrary exceptions to provider error
subclasses by matching common patterns (case-insensitive) in the exception
message. Subclasses can extend ``_ERROR_PATTERNS`` or override the method
entirely.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.providers.base import (
    ProviderBase,
    ProviderCapabilities,
    ProviderConnectionError,
    ProviderError,
    ProviderInfo,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


class _ConcreteProvider(ProviderBase):
    """Minimal concrete ProviderBase that does NOT override classify_error."""

    async def initialize(self, config: dict[str, Any]) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def get_status(self) -> ProviderInfo:
        return ProviderInfo(name="test", provider_type="test", is_available=True)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()


@pytest.fixture
def provider() -> _ConcreteProvider:
    return _ConcreteProvider()


class TestOverloadedPatterns:
    @pytest.mark.parametrize(
        "message",
        [
            "Server is overloaded",
            "Service at capacity, try later",
            "queue is full, please wait",
            "Engine OVERLOADED — too many requests",
            "We are at CAPACITY for the moment",
        ],
    )
    def test_maps_to_overloaded(self, provider: _ConcreteProvider, message: str) -> None:
        result = provider.classify_error(Exception(message))
        assert isinstance(result, ProviderOverloadedError)
        assert isinstance(result, ProviderError)


class TestRateLimitPatterns:
    @pytest.mark.parametrize(
        "message",
        [
            "rate limit exceeded",
            "Hit a Rate Limit, slow down",
            "HTTP 429 Too Many Requests",
            "Request returned 429",
        ],
    )
    def test_maps_to_rate_limit(self, provider: _ConcreteProvider, message: str) -> None:
        result = provider.classify_error(Exception(message))
        assert isinstance(result, ProviderRateLimitError)
        assert isinstance(result, ProviderError)


class TestConnectionPatterns:
    @pytest.mark.parametrize(
        "message",
        [
            "Connection refused",
            "connection reset by peer",
            "ConnectionError: failed to connect",
            "A ConnectionError occurred",
        ],
    )
    def test_maps_to_connection(self, provider: _ConcreteProvider, message: str) -> None:
        result = provider.classify_error(Exception(message))
        assert isinstance(result, ProviderConnectionError)
        assert isinstance(result, ProviderError)


class TestTimeoutPatterns:
    @pytest.mark.parametrize(
        "message",
        [
            "Request timeout",
            "Operation Timed Out after 30s",
            "Read timeout exceeded",
            "TIMED OUT waiting for response",
        ],
    )
    def test_maps_to_timeout(self, provider: _ConcreteProvider, message: str) -> None:
        result = provider.classify_error(Exception(message))
        assert isinstance(result, ProviderTimeoutError)
        assert isinstance(result, ProviderError)


class TestFallback:
    @pytest.mark.parametrize(
        "message",
        [
            "Something weird happened",
            "Invalid API key",
            "Bad request format",
            "",
            "Unknown failure",
        ],
    )
    def test_unmatched_falls_back_to_provider_error(
        self,
        provider: _ConcreteProvider,
        message: str,
    ) -> None:
        result = provider.classify_error(Exception(message))
        assert type(result) is ProviderError
        assert str(result) == message


class TestCaseInsensitive:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("OVERLOADED", ProviderOverloadedError),
            ("overloaded", ProviderOverloadedError),
            ("Overloaded", ProviderOverloadedError),
            ("oVeRlOaDeD", ProviderOverloadedError),
            ("RATE LIMIT", ProviderRateLimitError),
            ("Rate Limit", ProviderRateLimitError),
            ("CONNECTION FAILED", ProviderConnectionError),
            ("ConnectionError", ProviderConnectionError),
            ("TIMEOUT", ProviderTimeoutError),
            ("Timed Out", ProviderTimeoutError),
        ],
    )
    def test_mixed_case_matches(
        self,
        provider: _ConcreteProvider,
        message: str,
        expected: type[ProviderError],
    ) -> None:
        result = provider.classify_error(Exception(message))
        assert isinstance(result, expected)


class TestMessagePreservation:
    def test_overloaded_preserves_message(self, provider: _ConcreteProvider) -> None:
        result = provider.classify_error(Exception("Engine is overloaded"))
        assert "Engine is overloaded" in str(result)

    def test_fallback_preserves_message(self, provider: _ConcreteProvider) -> None:
        result = provider.classify_error(Exception("mystery failure"))
        assert str(result) == "mystery failure"


class TestSubclassExtension:
    def test_subclass_can_extend_patterns(self) -> None:
        class CustomProvider(_ConcreteProvider):
            _ERROR_PATTERNS = _ConcreteProvider._ERROR_PATTERNS + [
                (("poe", "atlas"), ProviderOverloadedError),
            ]

        provider = CustomProvider()
        result = provider.classify_error(Exception("poe service down"))
        assert isinstance(result, ProviderOverloadedError)

    def test_subclass_extension_does_not_break_base_patterns(self) -> None:
        class CustomProvider(_ConcreteProvider):
            _ERROR_PATTERNS = _ConcreteProvider._ERROR_PATTERNS + [
                (("poe", "atlas"), ProviderOverloadedError),
            ]

        provider = CustomProvider()
        result = provider.classify_error(Exception("rate limit exceeded"))
        assert isinstance(result, ProviderRateLimitError)


class TestSubclassOverride:
    def test_subclass_can_override_entirely(self) -> None:
        class CustomProvider(_ConcreteProvider):
            def classify_error(self, exc: Exception) -> ProviderError:
                if "auth" in str(exc).lower():
                    return ProviderError(f"AUTH: {exc}")
                return super().classify_error(exc)

        provider = CustomProvider()
        result = provider.classify_error(Exception("auth failed"))
        assert isinstance(result, ProviderError)
        assert str(result).startswith("AUTH:")

        overloaded = provider.classify_error(Exception("overloaded"))
        assert isinstance(overloaded, ProviderOverloadedError)


def test_classify_error_is_not_abstract() -> None:
    assert "classify_error" not in ProviderBase.__abstractmethods__


def test_concrete_provider_works_without_overriding_classify_error() -> None:
    provider = _ConcreteProvider()
    result = provider.classify_error(Exception("overloaded"))
    assert isinstance(result, ProviderOverloadedError)
