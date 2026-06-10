"""Tests for reddit_activity_tracker.fetcher (RedditSession)."""

import itertools
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import override_settings
from requests.exceptions import ConnectionError

from reddit_activity_tracker import fetcher

_REDDIT_SETTINGS = {
    "REDDIT_CLIENT_ID": "cid",
    "REDDIT_CLIENT_SECRET": "secret",
    "REDDIT_USER_AGENT": "test/1.0",
}
_NO_THROTTLE = {"REDDIT_REQUEST_INTERVAL": 0.0}


def _token_response(expires_in: int = 3600) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": "test-token", "expires_in": expires_in}
    resp.raise_for_status = MagicMock()
    return resp


def _api_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data if json_data is not None else {"ok": True}
    resp.raise_for_status = MagicMock(
        side_effect=(
            requests.exceptions.HTTPError(response=resp) if status >= 400 else None
        )
    )
    return resp


@override_settings(**_REDDIT_SETTINGS)
def test_build_session_success():
    session = fetcher.build_session()
    assert isinstance(session, fetcher.RedditSession)


@override_settings(
    REDDIT_CLIENT_ID="",
    REDDIT_CLIENT_SECRET="",
    REDDIT_USER_AGENT="",
)
def test_build_session_missing_env():
    with pytest.raises(EnvironmentError, match="REDDIT_CLIENT_ID"):
        fetcher.build_session()


@override_settings(**_REDDIT_SETTINGS, **_NO_THROTTLE)
@patch("reddit_activity_tracker.fetcher.time.time")
@patch("reddit_activity_tracker.fetcher.time.sleep")
def test_token_fetch_success(mock_sleep, mock_time):
    mock_time.side_effect = lambda: next(itertools.count(1000, 1))
    session = fetcher.RedditSession("cid", "secret", "ua/1.0")
    session._session.post = MagicMock(return_value=_token_response())
    session._session.get = MagicMock(
        return_value=_api_response(json_data={"data": {"children": []}})
    )

    result = session.get("/r/cpp/new", params={"limit": 5})

    assert result == {"data": {"children": []}}
    session._session.post.assert_called_once()
    assert "Bearer test-token" in session._session.headers["Authorization"]


@override_settings(**_NO_THROTTLE)
@patch("reddit_activity_tracker.fetcher.time.time")
def test_token_fetch_failure(mock_time):
    mock_time.side_effect = lambda: next(itertools.count(1000, 1))
    session = fetcher.RedditSession("cid", "secret", "ua/1.0")
    fail_resp = MagicMock()
    fail_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=fail_resp
    )
    session._session.post = MagicMock(return_value=fail_resp)

    with pytest.raises(requests.exceptions.HTTPError):
        session.get("/r/cpp/new")


@override_settings(**_NO_THROTTLE)
@patch("reddit_activity_tracker.fetcher.time.time")
@patch("reddit_activity_tracker.fetcher.time.sleep")
def test_429_retry_and_backoff(mock_sleep, mock_time):
    mock_time.side_effect = lambda: next(itertools.count(1000, 1))
    session = fetcher.RedditSession("cid", "secret", "ua/1.0")
    session._session.post = MagicMock(return_value=_token_response())
    session._session.get = MagicMock(
        side_effect=[
            _api_response(status=429),
            _api_response(status=429),
            _api_response(json_data={"ok": True}),
        ]
    )

    result = session.get("/r/cpp/new")

    assert result == {"ok": True}
    assert session._session.get.call_count == 3
    assert mock_sleep.call_count >= 2


@override_settings(**_NO_THROTTLE)
@patch("reddit_activity_tracker.fetcher.time.time")
@patch("reddit_activity_tracker.fetcher.time.sleep")
def test_401_mid_run_token_refresh(mock_sleep, mock_time):
    mock_time.side_effect = lambda: next(itertools.count(1000, 1))
    session = fetcher.RedditSession("cid", "secret", "ua/1.0")
    session._session.post = MagicMock(return_value=_token_response())
    session._session.get = MagicMock(
        side_effect=[
            _api_response(status=401),
            _api_response(json_data={"refreshed": True}),
        ]
    )

    result = session.get("/r/cpp/new")

    assert result == {"refreshed": True}
    assert session._session.post.call_count == 2


@override_settings(**_NO_THROTTLE)
@patch("reddit_activity_tracker.fetcher.time.time")
@patch("reddit_activity_tracker.fetcher.time.sleep")
def test_network_error_retry(mock_sleep, mock_time):
    mock_time.side_effect = lambda: next(itertools.count(1000, 1))
    session = fetcher.RedditSession("cid", "secret", "ua/1.0")
    session._session.post = MagicMock(return_value=_token_response())
    session._session.get = MagicMock(
        side_effect=[
            ConnectionError("down"),
            _api_response(json_data={"ok": True}),
        ]
    )

    result = session.get("/r/cpp/new")

    assert result == {"ok": True}
    assert session._session.get.call_count == 2


@override_settings(**_NO_THROTTLE)
@patch("reddit_activity_tracker.fetcher.time.time")
@patch("reddit_activity_tracker.fetcher.time.sleep")
def test_all_retries_exhausted(mock_sleep, mock_time):
    mock_time.side_effect = lambda: next(itertools.count(1000, 1))
    session = fetcher.RedditSession("cid", "secret", "ua/1.0")
    session._session.post = MagicMock(return_value=_token_response())
    session._session.get = MagicMock(side_effect=ConnectionError("down"))

    with pytest.raises(ConnectionError):
        session.get("/r/cpp/new")

    assert session._session.get.call_count == fetcher.MAX_RETRIES
