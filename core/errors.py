"""
Structured failure classification for collectors and related jobs.

Use :func:`classify_failure` to map exceptions to a small stable set of categories
for logs, metrics, and alerting (machine-parseable ``failure_category`` field).
"""

from __future__ import annotations

import errno
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


# errno values typically tied to sockets, pipes, or remote endpoints (not plain disk/path).
_NETWORK_ERRNOS: frozenset[int] = frozenset(
    getattr(errno, name)
    for name in (
        "EPIPE",
        "ECONNRESET",
        "ECONNREFUSED",
        "ENOTCONN",
        "ECONNABORTED",
        "ENETUNREACH",
        "EHOSTUNREACH",
        "ENETDOWN",
        "ETIMEDOUT",
        "EADDRINUSE",
        "EADDRNOTAVAIL",
        "ENETRESET",
        "ESHUTDOWN",
        "EMSGSIZE",
        "ENOBUFS",
    )
    if hasattr(errno, name)
)

# Typical local filesystem / resource exhaustion (not "network" for alerting).
_LOCAL_IO_ERRNOS: frozenset[int] = frozenset(
    getattr(errno, name)
    for name in (
        "ENOENT",
        "ENOTDIR",
        "EISDIR",
        "ENOSPC",
        "EROFS",
        "EBUSY",
        "EXDEV",
        "ENOTEMPTY",
        "ELOOP",
        "EMFILE",
        "ENFILE",
    )
    if hasattr(errno, name)
)

# Windows Winsock error codes that indicate transport/session failure (not errno-based).
_WIN_SOCK_WINERRORS: frozenset[int] = frozenset(
    {
        10013,  # WSAEACCES
        10014,  # WSAEFAULT
        10035,  # WSAEWOULDBLOCK
        10048,  # WSAEADDRINUSE
        10049,  # WSAEADDRNOTAVAIL
        10050,  # WSAENETDOWN
        10051,  # WSAENETUNREACH
        10052,  # WSAENETRESET
        10053,  # WSAECONNABORTED
        10054,  # WSAECONNRESET
        10055,  # WSAENOBUFS
        10057,  # WSAENOTCONN
        10058,  # WSAESHUTDOWN
        10060,  # WSAETIMEDOUT
        10061,  # WSAECONNREFUSED
        10064,  # WSAEHOSTDOWN
        10065,  # WSAEHOSTUNREACH
    }
)


def _os_error_windows_code(exc: OSError) -> int | None:
    """Windows code from ``exc.winerror``, or from ``exc.args[3]`` on POSIX (ignored slot)."""
    win = getattr(exc, "winerror", None)
    if isinstance(win, int):
        return win
    if len(exc.args) >= 4 and isinstance(exc.args[3], int):
        return exc.args[3]
    return None


def _classify_os_error(exc: OSError) -> CollectorFailureCategory:
    """
    ``OSError`` spans sockets/pipes and filesystem/disk; only classify clear network
    signals as :attr:`CollectorFailureCategory.NETWORK`.
    """
    if isinstance(
        exc,
        (
            FileNotFoundError,
            FileExistsError,
            IsADirectoryError,
            NotADirectoryError,
        ),
    ):
        return CollectorFailureCategory.UNKNOWN

    # ``ConnectionError`` and its subclasses cover refused/reset/aborted/broken pipe.
    if isinstance(exc, ConnectionError):
        return CollectorFailureCategory.NETWORK

    errno_val = exc.errno
    if errno_val is not None:
        if errno_val in _NETWORK_ERRNOS:
            return CollectorFailureCategory.NETWORK
        if errno_val in _LOCAL_IO_ERRNOS:
            return CollectorFailureCategory.UNKNOWN

    win_code = _os_error_windows_code(exc)
    if win_code is not None and win_code in _WIN_SOCK_WINERRORS:
        return CollectorFailureCategory.NETWORK

    return CollectorFailureCategory.UNKNOWN


def classify_failure(exc: BaseException) -> CollectorFailureCategory:
    """
    Map an exception to a failure category for structured logging.

    **Django:** :class:`~django.core.management.base.CommandError` and
    :class:`~django.core.exceptions.ValidationError` are recognized when Django is
    importable; if those imports fail (e.g. unusual test doubles), matching exceptions
    fall through to :attr:`~CollectorFailureCategory.UNKNOWN`. All
    :class:`~django.db.Error` subclasses map to :attr:`~CollectorFailureCategory.UNKNOWN`
    (schema vs transport ambiguity—override :meth:`handle_error` on the collector when
    you need finer buckets).

    **HTTP clients:** ``requests`` / ``urllib3`` / ``httpx`` exceptions are classified
    by module and type name; ``requests.HTTPError`` with ``response.status_code`` 429
    maps to :attr:`~CollectorFailureCategory.RATE_LIMIT`; 401 and 403 map to
    :attr:`~CollectorFailureCategory.AUTH`.

    **discord.py:** ``discord.errors.HTTPException`` and related types use ``status``
    when present (429 → rate limit; 401/403 → auth; 5xx → network; other 4xx → unknown).
    ``HTTPException`` without a status is treated as network; ``LoginFailure`` and
    similar map to auth.

    **slack_sdk:** Exceptions use ``response.status_code`` when present; otherwise
    :attr:`~CollectorFailureCategory.UNKNOWN`.

    Everything else maps to :attr:`~CollectorFailureCategory.UNKNOWN` unless it matches
    built-ins (for example :class:`OSError`, :class:`ValueError`) handled below.

    Args:
        exc: Any exception raised during collector work.

    Returns:
        A :class:`CollectorFailureCategory` member (use ``.value`` for logs).
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

    try:
        from django.db import Error as DjangoDBError
    except ImportError:
        DjangoDBError = ()  # type: ignore[misc, assignment]
    if DjangoDBError and isinstance(exc, DjangoDBError):
        return CollectorFailureCategory.UNKNOWN

    if isinstance(exc, PermissionError):
        return CollectorFailureCategory.PERMISSION
    if isinstance(exc, (TimeoutError,)):
        return CollectorFailureCategory.TIMEOUT

    # HTTP client libraries (optional deps)
    exc_mod = type(exc).__module__
    exc_name = type(exc).__name__
    if exc_mod.startswith("requests.exceptions"):
        if exc_name == "HTTPError":
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            if status == 429:
                return CollectorFailureCategory.RATE_LIMIT
            if status in (401, 403):
                return CollectorFailureCategory.AUTH
            return CollectorFailureCategory.NETWORK
        if exc_name == "SSLError":
            return CollectorFailureCategory.NETWORK
        if exc_name.endswith("Timeout"):
            return CollectorFailureCategory.TIMEOUT
        if exc_name in ("ConnectionError", "ChunkedEncodingError"):
            return CollectorFailureCategory.NETWORK
    if exc_mod.startswith("urllib3.exceptions"):
        if exc_name.endswith("TimeoutError"):
            return CollectorFailureCategory.TIMEOUT
        return CollectorFailureCategory.NETWORK
    if exc_mod.startswith("httpx"):
        if "Timeout" in exc_name:
            return CollectorFailureCategory.TIMEOUT
        if "HTTPStatus" in exc_name or "Transport" in exc_name or "Connect" in exc_name:
            return CollectorFailureCategory.NETWORK

    # discord.py (optional dependency): HTTPException and subclasses expose ``status``.
    if exc_mod.startswith("discord"):
        status = getattr(exc, "status", None)
        if isinstance(status, int):
            if status == 429:
                return CollectorFailureCategory.RATE_LIMIT
            if status in (401, 403):
                return CollectorFailureCategory.AUTH
            if 500 <= status < 600:
                return CollectorFailureCategory.NETWORK
            if 400 <= status < 500:
                return CollectorFailureCategory.UNKNOWN
            return CollectorFailureCategory.NETWORK
        if exc_name == "HTTPException":
            return CollectorFailureCategory.NETWORK
        if exc_name in ("LoginFailure", "PrivilegedIntentsRequired", "ClientException"):
            return CollectorFailureCategory.AUTH

    if exc_mod.startswith("slack_sdk"):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            if status == 429:
                return CollectorFailureCategory.RATE_LIMIT
            if status in (401, 403):
                return CollectorFailureCategory.AUTH
            if status >= 500:
                return CollectorFailureCategory.NETWORK
            if status >= 400:
                return CollectorFailureCategory.NETWORK
        return CollectorFailureCategory.UNKNOWN

    if isinstance(exc, OSError):
        return _classify_os_error(exc)

    if isinstance(exc, ValueError):
        # Often validation-ish in collectors
        return CollectorFailureCategory.VALIDATION

    return CollectorFailureCategory.UNKNOWN
