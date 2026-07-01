"""
Structured failure classification for collectors and related jobs.

Use :func:`classify_failure` to map exceptions to a small stable set of categories
for logs, metrics, and alerting (machine-parseable ``failure_category`` field).
"""

from __future__ import annotations

import errno
import re
from enum import Enum


class AuthenticationError(RuntimeError):
    """Raised when collector credentials are rejected (HTTP 401/403 or equivalent)."""


class CollectorValidationError(ValueError):
    """Raised when an API payload fails validation at a collector ingestion boundary."""


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


def _sanitize_credential_text(text: str) -> str:
    """Redact credentials from exception/log text snippets."""
    if not text:
        return text
    out = re.sub(
        r"(?i)([?&]key=)[^&\s\"'<>]+",
        r"\1<redacted>",
        text,
    )
    out = re.sub(
        r"(?i)([?&]token=)[^&\s\"'<>]+",
        r"\1<redacted>",
        out,
    )
    out = re.sub(
        r"(?i)(Authorization:\s*Bearer\s+)\S+",
        r"\1<redacted>",
        out,
    )
    out = re.sub(
        r"xox[bp]-[\w-]+",
        lambda m: m.group(0)[:5] + "<redacted>",
        out,
    )
    out = re.sub(
        r"(?i)(x-access-token:)[^@\s]+(@)",
        r"\1***\2",
        out,
    )
    out = re.sub(
        r"(?i)(https?://)[^/\s?#]+@",
        r"\1<redacted>@",
        out,
    )
    return out


def sanitize_exception_message(exc: BaseException) -> str:
    """
    Return a redacted string form of *exc* safe for logs.

    Redacts known credential patterns in the exception representation: URL query
    params ``key`` and ``token``, ``Authorization: Bearer`` values, Slack
    ``xoxb-`` / ``xoxp-`` tokens, GitHub ``x-access-token`` userinfo, and generic
    URL userinfo. Does not mutate *exc*; callers should still re-raise the original
    exception.
    """
    return _sanitize_credential_text(str(exc))


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
    via :func:`~core.failure_classifiers.classify_third_party_failure` using
    ``isinstance`` against SDK exception types; ``requests.HTTPError`` with
    ``response.status_code`` 429 maps to :attr:`~CollectorFailureCategory.RATE_LIMIT`;
    401 and 403 map to :attr:`~CollectorFailureCategory.AUTH`.

    **discord.py:** ``discord.errors.HTTPException`` and related types use ``status``
    when present (429 → rate limit; 401/403 → auth; 5xx → network; other 4xx → unknown).
    ``HTTPException`` without a status is treated as network; ``LoginFailure`` and
    similar map to auth.

    **slack_sdk:** Exceptions use ``response.status_code`` when present; otherwise
    :attr:`~CollectorFailureCategory.UNKNOWN`.

    **App validation:** Subclasses of :class:`CollectorValidationError` map to
    :attr:`~CollectorFailureCategory.VALIDATION` regardless of module path.

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
    if isinstance(exc, AuthenticationError):
        return CollectorFailureCategory.AUTH

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

    from core.failure_classifiers import classify_third_party_failure

    third_party = classify_third_party_failure(exc)
    if third_party is not None:
        return third_party

    if isinstance(exc, OSError):
        return _classify_os_error(exc)

    if isinstance(exc, CollectorValidationError):
        return CollectorFailureCategory.VALIDATION

    if isinstance(exc, ValueError):
        # Often validation-ish in collectors
        return CollectorFailureCategory.VALIDATION

    try:
        from pydantic import ValidationError as PydanticValidationError
    except ImportError:
        PydanticValidationError = ()  # type: ignore[misc, assignment]
    if PydanticValidationError and isinstance(exc, PydanticValidationError):
        return CollectorFailureCategory.VALIDATION

    return CollectorFailureCategory.UNKNOWN
