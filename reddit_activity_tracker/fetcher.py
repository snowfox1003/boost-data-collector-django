"""
Reddit OAuth API client for reddit_activity_tracker.

Ported from reddit-scraper/scraper.py (RedditSession + build_session).
"""

from __future__ import annotations

import logging
import random
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0


class RedditSession:
    """Thin wrapper around requests.Session that handles OAuth for Reddit."""

    _TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    _API_BASE = "https://oauth.reddit.com"

    def __init__(self, client_id: str, client_secret: str, user_agent: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._token_expiry: float = 0.0
        self._last_request_at: float = 0.0

    def _refresh_token(self) -> None:
        logger.info("Obtaining OAuth token...")
        auth = requests.auth.HTTPBasicAuth(self._client_id, self._client_secret)
        resp = self._session.post(
            self._TOKEN_URL,
            auth=auth,
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._session.headers["Authorization"] = f"Bearer {payload['access_token']}"
        self._token_expiry = time.time() + payload.get("expires_in", 3600) - 60
        logger.info(
            "OAuth token obtained (valid for ~%ds)",
            payload.get("expires_in", 3600),
        )

    def _ensure_token(self) -> None:
        if time.time() >= self._token_expiry:
            self._refresh_token()

    def _throttle(self) -> None:
        """Enforce a minimum gap between requests."""
        elapsed = time.time() - self._last_request_at
        interval = settings.REDDIT_REQUEST_INTERVAL
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_at = time.time()

    def get(self, path: str, params: dict | None = None) -> dict:
        """
        GET from the Reddit OAuth API with rate-limit enforcement and
        exponential backoff on 429 / transient errors.
        """
        self._ensure_token()
        url = f"{self._API_BASE}{path}"
        delay = RETRY_BASE_DELAY

        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=30)
            except requests.exceptions.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise
                wait = delay + random.uniform(0, 1)
                logger.warning(
                    "Network error (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
                delay *= 2
                continue

            if resp.status_code == 401:
                logger.warning("Token expired mid-run, refreshing...")
                self._refresh_token()
                continue

            if resp.status_code == 429:
                wait = delay + random.uniform(0, 1)
                logger.warning(
                    "Rate limited (429) on attempt %d/%d — retrying in %.1fs",
                    attempt,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                delay *= 2
                continue

            if resp.status_code != 200:
                if attempt == MAX_RETRIES:
                    resp.raise_for_status()
                wait = delay + random.uniform(0, 1)
                logger.warning(
                    "HTTP %d on attempt %d/%d — retrying in %.1fs",
                    resp.status_code,
                    attempt,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                delay *= 2
                continue

            return resp.json()

        raise RuntimeError(f"All {MAX_RETRIES} retries exhausted for {url}")


def build_session() -> RedditSession:
    """Build a RedditSession from Django settings (REDDIT_*)."""
    client_id = settings.REDDIT_CLIENT_ID
    client_secret = settings.REDDIT_CLIENT_SECRET
    user_agent = settings.REDDIT_USER_AGENT

    if not all([client_id, client_secret, user_agent]):
        raise EnvironmentError(
            "Missing one or more required settings: "
            "REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT"
        )

    return RedditSession(client_id, client_secret, user_agent)
