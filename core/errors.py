"""
Structured failure classification for collectors and related jobs.

Use :func:`classify_failure` to map exceptions to a small stable set of categories
for logs, metrics, and alerting (machine-parseable ``failure_category`` field).
"""

from __future__ import annotations

from enum import Enum


class CollectorFailureCategory(str, Enum):
    """High-level failure bucket for collector runs."""

    UNKNOWN = "unknown"
    VALIDATION = "validation"
    AUTH = "auth"
    PERMISSION = "permission"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    TIMEOUT = "timeout"
    COMMAND = "command"


def classify_failure(exc: BaseException) -> CollectorFailureCategory:
    """
    Map an exception to a failure category for structured logging.

    Keep this conservative: unknown is fine when we cannot infer intent.
    """
    # Django / app
    try:
        from django.core.exceptions import ValidationError
    except ImportError:
        ValidationError = ()  # type: ignore[misc, assignment]

    try:
        from django.core.management.base import CommandError
    except ImportError:
        CommandError = ()  # type: ignore[misc, assignment]

    if CommandError and isinstance(exc, CommandError):
        return CollectorFailureCategory.COMMAND
    if ValidationError and isinstance(exc, ValidationError):
        return CollectorFailureCategory.VALIDATION

    if isinstance(exc, PermissionError):
        return CollectorFailureCategory.PERMISSION
    if isinstance(exc, (TimeoutError,)):
        return CollectorFailureCategory.TIMEOUT

    # HTTP client libraries (optional deps)
    exc_mod = type(exc).__module__
    exc_name = type(exc).__name__
    if exc_mod.startswith("requests.exceptions"):
        if exc_name in ("HTTPError", "SSLError"):
            return CollectorFailureCategory.NETWORK
        if exc_name == "Timeout":
            return CollectorFailureCategory.TIMEOUT
        if exc_name in ("ConnectionError", "ChunkedEncodingError"):
            return CollectorFailureCategory.NETWORK
    if exc_mod.startswith("urllib3.exceptions"):
        return CollectorFailureCategory.NETWORK
    if exc_mod.startswith("httpx"):
        if "Timeout" in exc_name:
            return CollectorFailureCategory.TIMEOUT
        if "HTTPStatus" in exc_name or "Transport" in exc_name or "Connect" in exc_name:
            return CollectorFailureCategory.NETWORK

    if isinstance(exc, OSError):
        # Broken pipe, reset by peer, etc.
        return CollectorFailureCategory.NETWORK

    if isinstance(exc, ValueError):
        # Often validation-ish in collectors
        return CollectorFailureCategory.VALIDATION

    return CollectorFailureCategory.UNKNOWN
