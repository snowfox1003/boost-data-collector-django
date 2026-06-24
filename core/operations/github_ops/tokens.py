"""
GitHub token resolution: get token or API client by use case (scraping, push, write).

Scraping tokens use a shared ``itertools.cycle`` for round-robin via
:class:`_ScrapingTokenRoundRobin`.

Concurrency topology and annotation conventions: :doc:`docs/CONCURRENCY`.
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
from typing import Literal, final

import requests
from django.conf import settings

from core.operations.github_ops.client import (
    ConnectionException,
    GitHubAPIClient,
    RateLimitException,
)

logger = logging.getLogger(__name__)

_GITHUB_TOKEN_USES = ("scraping", "push", "create_pr", "write")


@final
class _ScrapingTokenRoundRobin:
    """Process-global round-robin over GITHUB_TOKENS_SCRAPING.

    Protects lazy ``itertools.cycle`` creation and each ``next()`` call.
    ``itertools.cycle`` is not safe to advance from multiple threads without
    serialization. Standalone lock — no ordering constraints with other locks.
    """

    def __init__(self) -> None:
        self._cycle: itertools.cycle | None = None
        self._lock = threading.Lock()

    def next_token(self, tokens: list[str]) -> str:
        with self._lock:
            if self._cycle is None:
                self._cycle = itertools.cycle(tokens)
            return next(self._cycle)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._cycle = None


_round_robin = _ScrapingTokenRoundRobin()


def get_github_token(
    use: Literal["scraping", "push", "create_pr", "write"] = "scraping",
) -> str:
    """
    Return the appropriate GitHub token for the given use case.

    - scraping: one of GITHUB_TOKENS_SCRAPING (round-robin) or GITHUB_TOKEN fallback
    - push: same as write (GITHUB_TOKEN_WRITE or GITHUB_TOKEN)
    - create_pr: same as write (GITHUB_TOKEN_WRITE or GITHUB_TOKEN)
    - write: GITHUB_TOKEN_WRITE (create PR, issues, comments, git push) or GITHUB_TOKEN

    Note:
        **Thread safety:** ``use="scraping"`` with multiple configured tokens is
        **thread-safe** (serialized via :class:`_ScrapingTokenRoundRobin`). Other
        uses read Django settings / environment; **thread-safe** when settings are
        not mutated concurrently during reads (typical deployment assumption).
    """
    if use not in _GITHUB_TOKEN_USES:
        raise ValueError(f"Unknown use {use!r}; valid: {', '.join(_GITHUB_TOKEN_USES)}")
    if use == "scraping":
        raw_tokens = getattr(settings, "GITHUB_TOKENS_SCRAPING", None) or []
        # Only include non-empty strings (skip whitespace-only or non-string entries)
        tokens = [t.strip() for t in raw_tokens if isinstance(t, str) and t.strip()]
        if tokens:
            return _round_robin.next_token(tokens)
        else:
            token = (
                getattr(settings, "GITHUB_TOKEN", None)
                or os.environ.get("GITHUB_TOKEN", "")
                or ""
            ).strip()
            if not token:
                raise ValueError(
                    "No scraping token: set GITHUB_TOKENS_SCRAPING or GITHUB_TOKEN."
                )
            return token

    if use in ("push", "create_pr", "write"):
        token = (
            getattr(settings, "GITHUB_TOKEN_WRITE", None)
            or getattr(settings, "GITHUB_TOKEN", None)
            or os.environ.get("GITHUB_TOKEN", "")
            or ""
        ).strip()
        if not token:
            raise ValueError("No write token: set GITHUB_TOKEN_WRITE or GITHUB_TOKEN.")
        return token


def get_github_client(
    use: Literal["scraping", "push", "create_pr", "write"] = "scraping",
) -> GitHubAPIClient | None:
    """
    Get a GitHub API client with the token for the given use case.

    Note:
        **Thread safety:** Inherits :func:`get_github_token` contract. Returns a new
        client per call; callers must not share one :class:`GitHubAPIClient` across
        threads unless they provide their own synchronization.
    """
    try:
        token = get_github_token(use=use)
    except ValueError as e:
        logger.error("Error getting GitHub token: %s", e)
        return None
    if not token:
        logger.error("No GitHub token")
        return None
    logger.debug("Creating GitHub API client (use=%s)", use)
    return GitHubAPIClient(token)


def validate_github_token_for_use(
    use: Literal["scraping", "push", "create_pr", "write"] = "scraping",
) -> None:
    """
    Confirm the resolved token exists and is accepted by GitHub (GET /user).

    Raises:
        ValueError: Unknown ``use``, missing token (from :func:`get_github_token`),
            rejected credentials (401/403), rate limit while validating, unreachable
            GitHub, or other HTTP/API failures during check.

    Note:
        **Thread safety:** Safe to call from multiple threads for independent
        validation runs. Concurrent validation of the same token may hit GitHub
        rate limits.
    """
    label = "scraping" if use == "scraping" else "write"
    # Resolve token outside get_github_client so ValueError (unknown use, missing token)
    # is not turned into None and misreported as "not configured".
    try:
        token = get_github_token(use=use)
    except ValueError:
        raise
    if not token:
        raise ValueError(
            f"No GitHub {label} token configured (see docs for GITHUB_TOKENS_SCRAPING / "
            "GITHUB_TOKEN or GITHUB_TOKEN_WRITE)."
        )
    client = GitHubAPIClient(token)
    try:
        client.rest_request("/user")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status in (401, 403):
            raise ValueError(
                f"GitHub {label} token is invalid or not authorized (HTTP {status}). "
                "Update GITHUB_TOKENS_SCRAPING / GITHUB_TOKEN or GITHUB_TOKEN_WRITE."
            ) from e
        raise ValueError(
            f"GitHub API error while validating {label} token (HTTP {status})."
        ) from e
    except RateLimitException as e:
        raise ValueError(
            f"GitHub rate limit exceeded while validating {label} token: {e}"
        ) from e
    except ConnectionException as e:
        raise ValueError(
            f"Could not reach GitHub to validate {label} token: {e}"
        ) from e
