"""Centralised error classification for AI provider failures.

Single source of truth that replaces the quadruplicated error-mapping
logic previously scattered across media generation services,
workers/tasks, and plugins/base.
"""

from dataclasses import dataclass

from app.services.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.services.video_processor import InvalidVideoOutputError


@dataclass(frozen=True)
class ClassifiedError:
    message: str
    recoverable: bool
    category: str


_RECOVERABLE_CATEGORIES = frozenset(
    {
        "overloaded",
        "rate_limit",
        "connection",
        "timeout",
        "server_error",
        "temporary",
    }
)

_STRING_PATTERNS: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("overloaded", "capacity", "queue is full"),
        "AI service is busy, please try again later",
        "overloaded",
    ),
    (
        ("rate limit", "429", "too many requests"),
        "Too many requests, please try again later",
        "rate_limit",
    ),
    (
        ("connection", "connectionerror", "connection refused"),
        "Connection failed, please check your network",
        "connection",
    ),
    (
        ("timeout", "timed out"),
        "Request timed out, please try again later",
        "timeout",
    ),
    (
        ("no data", "no output"),
        "generation returned no data, please try again",
        "no_data",
    ),
    (
        ("returned no image", "returned no video"),
        "generation returned no data, please try again",
        "no_data",
    ),
    (
        ("503", "502", "server error", "internal server error"),
        "Server error, please try again later",
        "server_error",
    ),
    (
        ("temporary", "retry", "try again later"),
        "Temporary issue, please try again later",
        "temporary",
    ),
]


def classify_provider_error(exc: Exception) -> ClassifiedError:
    if isinstance(exc, InvalidVideoOutputError):
        msg = (
            f"Generated video failed validation "
            f"({exc.result.actual_frames} frames, expected {exc.result.expected_frames})"
        )
        return ClassifiedError(message=msg, recoverable=False, category="validation")

    if isinstance(exc, ProviderOverloadedError):
        return ClassifiedError(
            message="AI service is busy, please try again later",
            recoverable=True,
            category="overloaded",
        )

    if isinstance(exc, ProviderRateLimitError):
        return ClassifiedError(
            message="Too many requests, please try again later",
            recoverable=True,
            category="rate_limit",
        )

    if isinstance(exc, ProviderConnectionError):
        return ClassifiedError(
            message="Connection failed, please check your network",
            recoverable=True,
            category="connection",
        )

    if isinstance(exc, ProviderTimeoutError):
        return ClassifiedError(
            message="Request timed out, please try again later",
            recoverable=True,
            category="timeout",
        )

    if isinstance(exc, ProviderError):
        return ClassifiedError(
            message="generation service error, please try again",
            recoverable=False,
            category="provider",
        )

    if isinstance(exc, ConnectionError):
        return ClassifiedError(
            message="Connection failed, please check your network",
            recoverable=True,
            category="connection",
        )

    if isinstance(exc, TimeoutError):
        return ClassifiedError(
            message="Request timed out, please try again later",
            recoverable=True,
            category="timeout",
        )

    exc_msg = str(exc).lower()
    for patterns, message, category in _STRING_PATTERNS:
        if any(p in exc_msg for p in patterns):
            return ClassifiedError(
                message=message,
                recoverable=category in _RECOVERABLE_CATEGORIES,
                category=category,
            )

    return ClassifiedError(
        message="An error occurred, please try again",
        recoverable=False,
        category="unknown",
    )
