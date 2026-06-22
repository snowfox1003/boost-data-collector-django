"""Unit tests for reddit_activity_tracker.fetcher helpers (no live Reddit API)."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import override_settings

from reddit_activity_tracker.fetcher import (
    RedditSession,
    _credentials_configured,
    _is_bearer_expired,
    _jwt_expiry,
    _normalize_bearer,
    build_session,
)


def _make_jwt(exp: float | None) -> str:
    header = (
        base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    )
    payload_dict: dict[str, float] = {}
    if exp is not None:
        payload_dict["exp"] = exp
    payload = (
        base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).decode().rstrip("=")
    )
    return f"{header}.{payload}.sig"


def test_normalize_bearer_strips_prefix():
    assert _normalize_bearer("Bearer abc.def.ghi") == "abc.def.ghi"
    assert _normalize_bearer("  bearer token  ") == "token"


def test_jwt_expiry_reads_exp_claim():
    exp = time.time() + 3600
    token = _make_jwt(exp)
    assert _jwt_expiry(token) == pytest.approx(exp)


def test_jwt_expiry_returns_none_for_invalid_token():
    assert _jwt_expiry("not-a-jwt") is None
    assert _jwt_expiry(_make_jwt(None)) is None


def test_is_bearer_expired_respects_leeway():
    past = time.time() - 120
    future = time.time() + 3600
    assert _is_bearer_expired(_make_jwt(past)) is True
    assert _is_bearer_expired(_make_jwt(future)) is False
    assert _is_bearer_expired("opaque-token") is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("your_client_id", None),
        ("real-id", "real-id"),
    ],
)
def test_credentials_configured(value, expected):
    assert _credentials_configured(value) == expected


@override_settings(
    REDDIT_USER_AGENT="test-agent",
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
    REDDIT_BEARER_TOKEN="",
    REDDIT_SESSION_COOKIE="",
)
def test_build_session_uses_client_credentials():
    session = build_session()
    assert isinstance(session, RedditSession)
    assert session._client_id == "cid"
    assert session._client_secret == "secret"


@override_settings(
    REDDIT_USER_AGENT="test-agent",
    REDDIT_CLIENT_ID="",
    REDDIT_CLIENT_SECRET="",
    REDDIT_BEARER_TOKEN="",
    REDDIT_SESSION_COOKIE="",
)
def test_build_session_raises_when_no_credentials():
    with pytest.raises(EnvironmentError, match="No Reddit credentials"):
        build_session()


@override_settings(
    REDDIT_USER_AGENT="",
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
)
def test_build_session_requires_user_agent():
    with pytest.raises(EnvironmentError, match="REDDIT_USER_AGENT"):
        build_session()


@override_settings(
    REDDIT_USER_AGENT="test-agent",
    REDDIT_CLIENT_ID="",
    REDDIT_CLIENT_SECRET="",
    REDDIT_BEARER_TOKEN="",
    REDDIT_SESSION_COOKIE="",
)
def test_build_session_raises_when_bearer_expired():
    expired = _make_jwt(time.time() - 120)
    with override_settings(REDDIT_BEARER_TOKEN=expired):
        with pytest.raises(EnvironmentError, match="expired"):
            build_session()


@override_settings(
    REDDIT_USER_AGENT="test-agent",
    REDDIT_CLIENT_ID="",
    REDDIT_CLIENT_SECRET="",
    REDDIT_BEARER_TOKEN="",
    REDDIT_SESSION_COOKIE="cookie",
    REDDIT_CSRF_TOKEN="csrf",
)
@patch(
    "reddit_activity_tracker.fetcher.mint_bearer_from_session",
    return_value="fresh.jwt.sig",
)
def test_build_session_mints_from_session_cookie(mock_mint):
    session = build_session()
    mock_mint.assert_called_once_with("cookie", "test-agent", "csrf")
    assert session._session_cookie == "cookie"


def test_reddit_session_apply_bearer_sets_authorization_header():
    token = _make_jwt(time.time() + 3600)
    session = RedditSession(None, None, "agent", bearer_token=token)
    assert (
        session._session.headers["Authorization"]
        == f"Bearer {_normalize_bearer(token)}"
    )


def test_reddit_session_backoff_honors_retry_after():
    session = RedditSession("id", "secret", "agent")
    resp = MagicMock()
    resp.headers = {"Retry-After": "3"}
    with patch("reddit_activity_tracker.fetcher.random.uniform", return_value=0.5):
        assert session._backoff_seconds(resp, 1.0) == 3.5


def test_reddit_session_backoff_uses_rate_limit_reset():
    session = RedditSession("id", "secret", "agent")
    resp = MagicMock()
    resp.headers = {"X-Ratelimit-Reset": "2"}
    with patch("reddit_activity_tracker.fetcher.random.uniform", return_value=1.0):
        assert session._backoff_seconds(resp, 1.0) == 3.0


def test_reddit_session_backoff_default_delay_with_jitter():
    session = RedditSession("id", "secret", "agent")
    with patch("reddit_activity_tracker.fetcher.random.uniform", return_value=0.25):
        assert session._backoff_seconds(None, 2.0) == 2.25


def test_reddit_session_update_rate_limit_state():
    session = RedditSession("id", "secret", "agent")
    resp = requests.Response()
    resp.headers["X-Ratelimit-Remaining"] = "4.5"
    resp.headers["X-Ratelimit-Reset"] = "12"
    session._update_rate_limit_state(resp)
    assert session._remaining == 4.5
    assert session._reset == 12.0
