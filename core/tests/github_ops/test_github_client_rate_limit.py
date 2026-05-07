"""Targeted tests for GitHubAPIClient rate limiting and _do_request internals."""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.operations.github_ops.client import (
    RATE_LIMIT_WAIT_SAFETY_MARGIN_SEC,
    ConnectionException,
    GitHubAPIClient,
    RateLimitException,
)


def _resp(
    status,
    json_data=None,
    headers=None,
    json_side_effect=None,
):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    if json_side_effect is not None:
        r.json = MagicMock(side_effect=json_side_effect)
    else:
        r.json = MagicMock(return_value=json_data if json_data is not None else {})
    r.raise_for_status = MagicMock()
    return r


def test_check_rate_limit_success_updates_state():
    client = GitHubAPIClient("t")
    payload = {
        "resources": {
            "core": {"remaining": 42, "reset": int(time.time()) + 3600},
        },
    }
    client.session.get = MagicMock(return_value=_resp(200, payload))
    assert client._check_rate_limit() is True
    assert client.rate_limit_remaining == 42


def test_check_rate_limit_zero_remaining_raises_when_reset_future():
    client = GitHubAPIClient("t")
    reset = int(time.time()) + 120
    payload = {"resources": {"core": {"remaining": 0, "reset": reset}}}
    client.session.get = MagicMock(return_value=_resp(200, payload))
    with pytest.raises(RateLimitException, match="Rate limit exceeded"):
        client._check_rate_limit()


def test_check_rate_limit_connection_error_retries_then_raises():
    from requests.exceptions import ConnectionError as ReqCE

    client = GitHubAPIClient("t")
    client.session.get = MagicMock(side_effect=ReqCE("down"))
    with patch("core.operations.github_ops.client.time.sleep"):
        with pytest.raises(ConnectionException, match="Connection error after"):
            client._check_rate_limit()
    assert client.session.get.call_count == 3


def test_check_rate_limit_request_exception_raises():
    client = GitHubAPIClient("t")
    client.session.get = MagicMock(
        side_effect=requests.exceptions.RequestException("x")
    )
    with pytest.raises(requests.exceptions.RequestException):
        client._check_rate_limit()


def test_parse_rate_limit_wait_graphql_errors_in_200_body():
    client = GitHubAPIClient("t")
    r = _resp(200, {"errors": [{"message": "throttled"}]})
    wait = client._parse_rate_limit_wait(r)
    # Throttled GraphQL body without rate-limit headers falls through to None.
    assert wait is None


def test_parse_rate_limit_wait_200_json_decode_error():
    client = GitHubAPIClient("t")
    r = _resp(200, json_side_effect=ValueError("bad json"))
    assert client._parse_rate_limit_wait(r) is None


def test_parse_rate_limit_wait_retry_after_int():
    client = GitHubAPIClient("t")
    r = _resp(429, headers={"Retry-After": "10"})
    assert client._parse_rate_limit_wait(r) == 10


def test_parse_rate_limit_wait_retry_after_http_date():
    client = GitHubAPIClient("t")
    r = _resp(429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"})
    w = client._parse_rate_limit_wait(r)
    assert isinstance(w, (int, float))
    assert w > 0


def test_parse_rate_limit_wait_retry_after_invalid_then_x_ratelimit():
    client = GitHubAPIClient("t")
    future = int(time.time()) + 500
    r = _resp(
        403,
        headers={
            "Retry-After": "not-a-number-or-date",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(future),
        },
    )
    w = client._parse_rate_limit_wait(r)
    assert isinstance(w, int)
    assert w > 0


def test_parse_rate_limit_wait_non_403_429_returns_none():
    client = GitHubAPIClient("t")
    assert client._parse_rate_limit_wait(_resp(200, {})) is None


def test_parse_rate_limit_remaining_nonzero_returns_none():
    client = GitHubAPIClient("t")
    r = _resp(403, headers={"X-RateLimit-Remaining": "5", "X-RateLimit-Reset": "1"})
    assert client._parse_rate_limit_wait(r) is None


def test_update_rate_limit_from_response_skips_invalid_int():
    client = GitHubAPIClient("t")
    client.rate_limit_remaining = 77
    client.rate_limit_reset_time = 88
    r = _resp(200, headers={"X-RateLimit-Remaining": "x", "X-RateLimit-Reset": "1"})
    client._update_rate_limit_from_response(r)
    assert client.rate_limit_remaining == 77
    assert client.rate_limit_reset_time == 88


def test_raise_if_error_http_error_propagates():
    client = GitHubAPIClient("t")
    r = _resp(500)
    err = requests.exceptions.HTTPError(response=r)
    r.raise_for_status = MagicMock(side_effect=err)
    with pytest.raises(requests.exceptions.HTTPError):
        client._raise_if_error_and_update_rate_limit(r, "label")


def test_raise_if_error_request_exception_propagates():
    client = GitHubAPIClient("t")
    r = MagicMock()
    r.raise_for_status = MagicMock(
        side_effect=requests.exceptions.RequestException("boom")
    )
    with pytest.raises(requests.exceptions.RequestException):
        client._raise_if_error_and_update_rate_limit(r, "label")


def test_handle_rate_limit_caps_wait_and_calls_check(monkeypatch):
    client = GitHubAPIClient("t")
    slept = []

    monkeypatch.setattr(
        "core.operations.github_ops.client.time.sleep", lambda s: slept.append(s)
    )
    client._check_rate_limit = MagicMock(return_value=True)
    max_delay = 10
    client._handle_rate_limit(999_999, max_delay=max_delay)
    assert slept == [max_delay + RATE_LIMIT_WAIT_SAFETY_MARGIN_SEC]
    client._check_rate_limit.assert_called_once()


def test_do_request_rate_limit_wait_then_success():
    client = GitHubAPIClient("t")
    ok = _resp(200, {"ok": True})
    limited = _resp(429, headers={"Retry-After": "0", "X-RateLimit-Remaining": "0"})
    client.session.request = MagicMock(side_effect=[limited, ok])
    client._parse_rate_limit_wait = MagicMock(
        side_effect=[1, None],
    )
    client._handle_rate_limit = MagicMock()
    with patch("core.operations.github_ops.client.time.sleep"):
        out = client._do_request(
            "GET",
            "https://api.github.com/x",
            "/x",
            allow_retry_on_5xx=True,
            allow_retry_on_connection_errors=True,
        )
    assert out.status_code == 200


def test_do_request_connection_retry_then_success():
    from requests.exceptions import ConnectionError as ReqCE

    client = GitHubAPIClient("t")
    ok = _resp(200, {"a": 1})
    client.session.request = MagicMock(side_effect=[ReqCE("x"), ok])
    client._parse_rate_limit_wait = MagicMock(return_value=None)
    with patch("core.operations.github_ops.client.time.sleep"):
        out = client._do_request(
            "GET",
            "https://api.github.com/y",
            "/y",
            allow_retry_on_connection_errors=True,
        )
    assert out.json() == {"a": 1}
