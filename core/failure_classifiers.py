"""
Lazy isinstance-based classifiers for third-party SDK exceptions.

Each classifier imports SDK exception types at call time (not module load) so
test doubles swapped into SDK modules remain visible to :func:`classify_failure`.
"""

from __future__ import annotations

from core.errors import CollectorFailureCategory


def _match_registered_exception(
    exc: BaseException,
    module_name: str,
) -> tuple[type[BaseException], str] | None:
    """Return (exception class, attribute name) for the most specific match on *module_name*."""
    try:
        import importlib

        mod = importlib.import_module(module_name)
    except ImportError:
        return None

    best: tuple[type[BaseException], str] | None = None
    best_depth = -1
    for attr in dir(mod):
        if attr.startswith("_"):
            continue
        cls = getattr(mod, attr, None)
        if (
            isinstance(cls, type)
            and issubclass(cls, BaseException)
            and isinstance(exc, cls)
        ):
            depth = len(cls.__mro__)
            if depth > best_depth:
                best = (cls, attr)
                best_depth = depth
    return best


def _classify_requests(exc: BaseException) -> CollectorFailureCategory | None:
    matched = _match_registered_exception(exc, "requests.exceptions")
    if matched is None:
        return None
    _, name = matched

    if name == "HTTPError":
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if status == 429:
            return CollectorFailureCategory.RATE_LIMIT
        if status in (401, 403):
            return CollectorFailureCategory.AUTH
        return CollectorFailureCategory.NETWORK
    if name == "SSLError":
        return CollectorFailureCategory.NETWORK
    if name.endswith("Timeout"):
        return CollectorFailureCategory.TIMEOUT
    if name in ("ConnectionError", "ChunkedEncodingError"):
        return CollectorFailureCategory.NETWORK
    return None


def _classify_urllib3(exc: BaseException) -> CollectorFailureCategory | None:
    matched = _match_registered_exception(exc, "urllib3.exceptions")
    if matched is None:
        return None
    _, name = matched
    if name.endswith("TimeoutError"):
        return CollectorFailureCategory.TIMEOUT
    return CollectorFailureCategory.NETWORK


def _classify_httpx(exc: BaseException) -> CollectorFailureCategory | None:
    try:
        import httpx
    except ImportError:
        return None

    matched_name: str | None = None
    best_depth = -1
    for attr in dir(httpx):
        if attr.startswith("_"):
            continue
        cls = getattr(httpx, attr, None)
        if (
            isinstance(cls, type)
            and issubclass(cls, BaseException)
            and isinstance(exc, cls)
        ):
            depth = len(cls.__mro__)
            if depth > best_depth:
                matched_name = attr
                best_depth = depth
    if matched_name is None:
        return None
    if "Timeout" in matched_name:
        return CollectorFailureCategory.TIMEOUT
    if (
        "HTTPStatus" in matched_name
        or "Transport" in matched_name
        or "Connect" in matched_name
    ):
        return CollectorFailureCategory.NETWORK
    return None


def _classify_discord_http_status(
    status: int,
) -> CollectorFailureCategory:
    if status == 429:
        return CollectorFailureCategory.RATE_LIMIT
    if status in (401, 403):
        return CollectorFailureCategory.AUTH
    if 500 <= status < 600:
        return CollectorFailureCategory.NETWORK
    if 400 <= status < 500:
        return CollectorFailureCategory.UNKNOWN
    return CollectorFailureCategory.NETWORK


def _classify_discord(exc: BaseException) -> CollectorFailureCategory | None:
    matched = _match_registered_exception(exc, "discord.errors")
    if matched is None:
        return None
    _, name = matched

    if name in ("LoginFailure", "PrivilegedIntentsRequired", "ClientException"):
        return CollectorFailureCategory.AUTH
    if name == "HTTPException":
        status = getattr(exc, "status", None)
        if isinstance(status, int):
            return _classify_discord_http_status(status)
        return CollectorFailureCategory.NETWORK

    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return _classify_discord_http_status(status)
    return CollectorFailureCategory.UNKNOWN


def _classify_slack_sdk(exc: BaseException) -> CollectorFailureCategory | None:
    matched = _match_registered_exception(exc, "slack_sdk.errors")
    if matched is None:
        return None

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


_SDK_CLASSIFIERS = (
    _classify_requests,
    _classify_urllib3,
    _classify_httpx,
    _classify_discord,
    _classify_slack_sdk,
)


def classify_third_party_failure(
    exc: BaseException,
) -> CollectorFailureCategory | None:
    """Run ordered SDK classifiers; return the first non-None category."""
    for fn in _SDK_CLASSIFIERS:
        category = fn(exc)
        if category is not None:
            return category
    return None
