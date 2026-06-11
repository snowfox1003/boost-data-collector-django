"""Tests for git_ops worker session and GitHub 403 wait helper."""

import time
from unittest.mock import MagicMock


from core.operations.github_ops import git_ops as go


def test_get_worker_session_reuses_same_token():
    go._session_store.reset_for_tests()
    s1 = go._get_worker_session("same-token")
    s2 = go._get_worker_session("same-token")
    assert s1 is s2
    assert "Authorization" in s1.headers


def test_get_worker_session_new_session_when_token_changes():
    go._session_store.reset_for_tests()
    a = go._get_worker_session("token-a")
    b = go._get_worker_session("token-b")
    assert a is not b
    assert "token-a" in a.headers["Authorization"]
    assert "token-b" in b.headers["Authorization"]


def _mock_resp(headers):
    r = MagicMock()
    r.headers = headers
    return r


def test_wait_seconds_403_rate_limit_reset_path():
    future = int(time.time()) + 120
    r = _mock_resp(
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(future)},
    )
    w = go._wait_seconds_for_github_403(r, attempt=0)
    assert 1.0 <= w <= go._UPLOAD_FOLDER_403_MAX_SLEEP_SEC


def test_wait_seconds_403_invalid_remaining_falls_through_to_retry_after():
    r = _mock_resp({"X-RateLimit-Remaining": "nope", "Retry-After": "2"})
    w = go._wait_seconds_for_github_403(r, attempt=0)
    assert 1.0 <= w <= go._UPLOAD_FOLDER_403_MAX_SLEEP_SEC


def test_wait_seconds_403_retry_after_invalid_falls_back_exponential():
    r = _mock_resp({"Retry-After": "not-float"})
    w = go._wait_seconds_for_github_403(r, attempt=2)
    assert w >= 60.0


def test_wait_seconds_403_retry_after_too_small_becomes_one():
    r = _mock_resp({"Retry-After": "0.1"})
    w = go._wait_seconds_for_github_403(r, attempt=0)
    assert w >= 1.0
