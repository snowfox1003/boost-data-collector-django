"""
Reddit OAuth API client for reddit_activity_tracker.

Ported from reddit-scraper/scraper.py (RedditSession + build_session).
Supports client credentials, bearer token, or session-cookie auth.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import time
from datetime import datetime, timezone

import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0
RATE_LIMIT_LOW_WATERMARK = getattr(settings, "REDDIT_RATE_LIMIT_LOW_WATERMARK", 2.0)
_SHREDDIT_TOKEN_URL = "https://www.reddit.com/svc/shreddit/token"
_PLACEHOLDER_VALUES = frozenset({"your_client_id", "your_client_secret"})


def _normalize_bearer(token: str) -> str:
    token = token.strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


def _jwt_expiry(token: str) -> float | None:
    try:
        parts = _normalize_bearer(token).split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        return float(exp) if exp is not None else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _is_bearer_expired(token: str, leeway: float = 60) -> bool:
    exp = _jwt_expiry(token)
    if exp is None:
        return False
    return time.time() >= exp - leeway


def mint_bearer_from_session(
    session_cookie: str,
    user_agent: str,
    csrf_token: str | None = None,
) -> str:
    """Exchange a reddit_session cookie for a fresh token_v2 bearer JWT."""
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": user_agent,
            "Content-Type": "application/json",
            "Origin": "https://www.reddit.com",
        }
    )
    sess.cookies.set("reddit_session", session_cookie.strip(), domain=".reddit.com")

    csrf = csrf_token.strip() if csrf_token else None
    if csrf:
        sess.cookies.set("csrf_token", csrf, domain=".reddit.com")
    else:
        sess.get("https://www.reddit.com/", timeout=30)
        csrf = sess.cookies.get("csrf_token")

    if not csrf:
        raise RuntimeError(
            "Could not obtain csrf_token — set REDDIT_CSRF_TOKEN in .env "
            "(DevTools → Cookies → csrf_token)"
        )

    resp = sess.post(_SHREDDIT_TOKEN_URL, json={"csrf_token": csrf}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to mint bearer token from session (HTTP {resp.status_code})"
        )

    data = resp.json()
    token = data.get("token")
    if not token:
        raise RuntimeError("Reddit token endpoint returned no token")

    expires = data.get("expires")
    if expires:
        logger.info(
            "Minted bearer token from session (expires %s)",
            datetime.fromtimestamp(expires / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
        )
    else:
        logger.info("Minted bearer token from session")
    return token


def _credentials_configured(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    if value.strip() in _PLACEHOLDER_VALUES:
        return None
    return value.strip()


class RedditSession:
    """Thin wrapper around requests.Session that handles OAuth for Reddit."""

    _TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    _API_BASE = "https://oauth.reddit.com"

    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        user_agent: str,
        *,
        bearer_token: str | None = None,
        session_cookie: str | None = None,
        csrf_token: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._user_agent = user_agent
        self._session_cookie = session_cookie
        self._csrf_token = csrf_token
        self._bearer_mode = bearer_token is not None
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._token_expiry: float = 0.0
        self._last_request_at: float = 0.0
        self._remaining: float | None = None
        self._reset: float | None = None
        if bearer_token:
            self._apply_bearer(bearer_token)

    def _apply_bearer(self, token: str) -> None:
        token = _normalize_bearer(token)
        self._session.headers["Authorization"] = f"Bearer {token}"
        exp = _jwt_expiry(token)
        self._token_expiry = exp if exp is not None else float("inf")

    def _remint_bearer_from_session(self) -> None:
        if not self._session_cookie:
            raise RuntimeError(
                "Bearer token expired and no REDDIT_SESSION_COOKIE available to re-mint"
            )
        logger.info("Re-minting bearer token from REDDIT_SESSION_COOKIE...")
        self._apply_bearer(
            mint_bearer_from_session(
                self._session_cookie, self._user_agent, self._csrf_token
            )
        )

    def _refresh_token(self) -> None:
        if self._bearer_mode:
            self._remint_bearer_from_session()
            return
        logger.info("Obtaining OAuth token...")
        if not self._client_id or not self._client_secret:
            raise RuntimeError("Reddit OAuth client_id and client_secret are required")
        auth = HTTPBasicAuth(self._client_id, self._client_secret)
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
        if self._bearer_mode:
            if time.time() >= self._token_expiry and self._session_cookie:
                self._remint_bearer_from_session()
            return
        if time.time() >= self._token_expiry:
            self._refresh_token()

    def _update_rate_limit_state(self, resp: requests.Response) -> None:
        remaining = resp.headers.get("X-Ratelimit-Remaining")
        reset = resp.headers.get("X-Ratelimit-Reset")
        if remaining is not None:
            self._remaining = float(remaining)
        if reset is not None:
            self._reset = float(reset)

    def _backoff_seconds(self, resp: requests.Response | None, delay: float) -> float:
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                return float(retry_after) + random.uniform(0, 1)
            reset = resp.headers.get("X-Ratelimit-Reset")
            if reset is not None:
                return float(reset) + random.uniform(0.5, 1.5)
        return delay + random.uniform(0, 1)

    def _throttle(self) -> None:
        if (
            self._remaining is not None
            and self._remaining < RATE_LIMIT_LOW_WATERMARK
            and self._reset is not None
        ):
            wait = max(self._reset, 0) + random.uniform(0.5, 1.5)
            logger.warning(
                "Rate limit low (%.1f remaining, reset in %.1fs) — sleeping %.1fs",
                self._remaining,
                self._reset,
                wait,
            )
            time.sleep(wait)
            self._remaining = None
            self._reset = None
            self._last_request_at = time.time()
            return

        elapsed = time.time() - self._last_request_at
        interval = settings.REDDIT_REQUEST_INTERVAL
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_at = time.time()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
    ) -> dict:
        self._ensure_token()
        url = f"{self._API_BASE}{path}"
        delay = RETRY_BASE_DELAY

        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                if method == "GET":
                    resp = self._session.get(url, params=params, timeout=30)
                else:
                    resp = self._session.post(url, data=data, timeout=30)
            except requests.exceptions.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise
                wait = self._backoff_seconds(None, delay)
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

            self._update_rate_limit_state(resp)

            if resp.status_code == 401:
                if self._bearer_mode:
                    if self._session_cookie and attempt < MAX_RETRIES:
                        logger.warning(
                            "Bearer token rejected — re-minting from session..."
                        )
                        self._remint_bearer_from_session()
                        continue
                    raise RuntimeError(
                        "Bearer token rejected — update REDDIT_BEARER_TOKEN or "
                        "REDDIT_SESSION_COOKIE in .env"
                    )
                logger.warning("Token expired mid-run, refreshing...")
                self._refresh_token()
                continue

            if resp.status_code == 429:
                wait = self._backoff_seconds(resp, delay)
                logger.warning(
                    "Rate limited (429) on attempt %d/%d — retrying in %.1fs",
                    attempt,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                self._remaining = None
                self._reset = None
                delay *= 2
                continue

            if resp.status_code != 200:
                if attempt == MAX_RETRIES:
                    resp.raise_for_status()
                wait = self._backoff_seconds(resp, delay)
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

            if (
                self._remaining is not None
                and self._remaining < RATE_LIMIT_LOW_WATERMARK
            ):
                logger.info(
                    "Rate limit quota low after request (%.1f remaining, reset in %.1fs)",
                    self._remaining,
                    self._reset or 0,
                )

            return resp.json()

        raise RuntimeError(f"All {MAX_RETRIES} retries exhausted for {url}")

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET from the Reddit OAuth API with rate-limit enforcement."""
        return self._request("GET", path, params=params)

    def fetch_user_about(self, username: str) -> dict | None:
        """Fetch /user/{username}/about; returns None for deleted/invalid users."""
        username = (username or "").strip()
        if not username or username in {"[deleted]", "AutoModerator"}:
            return None
        try:
            payload = self.get(f"/user/{username}/about", params={"raw_json": 1})
        except requests.exceptions.HTTPError:
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None

    def fetch_comments_in_range(
        self,
        start_ts: int,
        end_ts: int,
        *,
        subreddit: str,
    ) -> list[dict]:
        """Paginate /r/{subreddit}/comments and keep items created in range."""
        comments: list[dict] = []
        after: str | None = None

        logger.info(
            "Reddit: searching r/%s recent comments for %d..%d",
            subreddit,
            start_ts,
            end_ts,
        )

        while True:
            params: dict = {"limit": 100, "raw_json": 1}
            if after:
                params["after"] = after

            data = self.get(f"/r/{subreddit}/comments", params=params)
            listing = data.get("data", {})
            children = listing.get("children", [])

            if not children:
                break

            page_timestamps: list[int] = []
            for child in children:
                if child.get("kind") != "t1":
                    continue
                comment = child.get("data", {})
                created = int(comment.get("created_utc", 0))
                page_timestamps.append(created)
                if start_ts <= created <= end_ts:
                    comments.append(comment)

            if page_timestamps and min(page_timestamps) < start_ts:
                break

            after = listing.get("after")
            if not after:
                break

        logger.info("Reddit: fetched %d comments in range", len(comments))
        return comments

    def fetch_submissions_in_range(
        self,
        start_ts: int,
        end_ts: int,
        *,
        subreddit: str,
    ) -> list[dict]:
        """Paginate /r/{subreddit}/new and keep submissions created in range."""
        posts: dict[str, dict] = {}
        after: str | None = None

        logger.info(
            "Reddit: searching r/%s recent submissions for %d..%d",
            subreddit,
            start_ts,
            end_ts,
        )

        while True:
            params: dict = {"limit": 100, "raw_json": 1}
            if after:
                params["after"] = after

            data = self.get(f"/r/{subreddit}/new", params=params)
            listing = data.get("data", {})
            children = listing.get("children", [])

            if not children:
                break

            page_timestamps: list[int] = []
            for child in children:
                if child.get("kind") != "t3":
                    continue
                post = child.get("data", {})
                created = int(post.get("created_utc", 0))
                page_timestamps.append(created)
                if start_ts <= created <= end_ts:
                    posts[post["id"]] = post

            if page_timestamps and min(page_timestamps) < start_ts:
                break

            after = listing.get("after")
            if not after:
                break

        discovered = sorted(posts.values(), key=lambda post: int(post["created_utc"]))
        logger.info("Submission discovery found %d posts in range", len(discovered))
        return discovered


def build_session() -> RedditSession:
    """Build a RedditSession from Django settings (REDDIT_*)."""
    user_agent = settings.REDDIT_USER_AGENT
    if not user_agent:
        raise EnvironmentError("Missing required setting: REDDIT_USER_AGENT")

    client_id = _credentials_configured(settings.REDDIT_CLIENT_ID)
    client_secret = _credentials_configured(settings.REDDIT_CLIENT_SECRET)
    if client_id and client_secret:
        logger.info("Using official Reddit API (client credentials)")
        return RedditSession(client_id, client_secret, user_agent)

    bearer_raw = settings.REDDIT_BEARER_TOKEN
    session_cookie = settings.REDDIT_SESSION_COOKIE
    csrf_token = settings.REDDIT_CSRF_TOKEN

    if bearer_raw and not _is_bearer_expired(bearer_raw):
        logger.warning("Using REDDIT_BEARER_TOKEN")
        return RedditSession(
            None,
            None,
            user_agent,
            bearer_token=bearer_raw,
            session_cookie=session_cookie or None,
            csrf_token=csrf_token,
        )

    if session_cookie:
        bearer_token = mint_bearer_from_session(session_cookie, user_agent, csrf_token)
        return RedditSession(
            None,
            None,
            user_agent,
            bearer_token=bearer_token,
            session_cookie=session_cookie,
            csrf_token=csrf_token,
        )

    if bearer_raw:
        raise EnvironmentError(
            "REDDIT_BEARER_TOKEN is expired — paste a fresh token_v2 or set "
            "REDDIT_SESSION_COOKIE to auto-mint"
        )

    raise EnvironmentError(
        "No Reddit credentials configured. Set REDDIT_CLIENT_ID + "
        "REDDIT_CLIENT_SECRET, or REDDIT_BEARER_TOKEN, or REDDIT_SESSION_COOKIE"
    )
