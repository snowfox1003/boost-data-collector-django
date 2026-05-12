"""
GitHub token resolution: get token or API client by use case (scraping, push, write).

Scraping tokens use a shared ``itertools.cycle`` for round-robin. Lazy init and each
``next()`` run under ``_scraping_token_lock`` so concurrent callers (e.g. multiple
threads or Celery workers) cannot corrupt iterator state.
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
from typing import Literal, Optional

import requests
from django.conf import settings

from core.operations.github_ops.client import (
    ConnectionException,
    GitHubAPIClient,
    RateLimitException,
)

logger = logging.getLogger(__name__)

_scraping_token_cycle: Optional[itertools.cycle] = None
_scraping_token_lock = threading.Lock()

_GITHUB_TOKEN_USES = ("scraping", "push", "create_pr", "write")


def get_github_token(
    use: Literal["scraping", "push", "create_pr", "write"] = "scraping",
) -> str:
    """
    Return the appropriate GitHub token for the given use case.

    - scraping: one of GITHUB_TOKENS_SCRAPING (round-robin) or GITHUB_TOKEN fallback
    - push: same as write (GITHUB_TOKEN_WRITE or GITHUB_TOKEN)
    - create_pr: same as write (GITHUB_TOKEN_WRITE or GITHUB_TOKEN)
    - write: GITHUB_TOKEN_WRITE (create PR, issues, comments, git push) or GITHUB_TOKEN
    """
    if use not in _GITHUB_TOKEN_USES:
        raise ValueError(f"Unknown use {use!r}; valid: {', '.join(_GITHUB_TOKEN_USES)}")
    if use == "scraping":
        raw_tokens = getattr(settings, "GITHUB_TOKENS_SCRAPING", None) or []
        # Only include non-empty strings (skip whitespace-only or non-string entries)
        tokens = [t.strip() for t in raw_tokens if isinstance(t, str) and t.strip()]
        global _scraping_token_cycle
        if tokens:
            # Hold the lock for both cycle creation and next(): itertools.cycle is not
            # safe to advance from multiple threads without serialization.
            with _scraping_token_lock:
                if _scraping_token_cycle is None:
                    _scraping_token_cycle = itertools.cycle(tokens)
                return next(_scraping_token_cycle)
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
        ValueError: No token configured, rejected credentials (401/403), rate limit
            while validating, unreachable GitHub, or other HTTP/API failures during check.
    """
    label = "scraping" if use == "scraping" else "write"
    client = get_github_client(use=use)
    if client is None:
        raise ValueError(
            f"No GitHub {label} token configured (see docs for GITHUB_TOKENS_SCRAPING / "
            "GITHUB_TOKEN or GITHUB_TOKEN_WRITE)."
        )
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
