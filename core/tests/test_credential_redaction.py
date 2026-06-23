"""Tests for credential redaction in exception messages and collector error logging."""

from __future__ import annotations

import traceback
from unittest.mock import patch

import pytest

import core.collectors.base_collector as collector_lifecycle
from core.collectors.base_collector import AbstractCollector, _safe_exc_info
from core.errors import sanitize_exception_message
from core.tracker_result import GenericTrackerResult

_OK = GenericTrackerResult.ok()


def _http_error_with_secret_url():
    pytest.importorskip("requests")
    import requests

    url = "https://api.example.com/v1/data?key=SECRET_KEY&other=keep"
    resp = requests.Response()
    resp.status_code = 500
    resp.url = url
    return requests.HTTPError(
        f"500 Server Error: Internal for url: {url}",
        response=resp,
    )


def test_sanitize_exception_message_http_error_redacts_key_query_param():
    exc = _http_error_with_secret_url()
    out = sanitize_exception_message(exc)
    assert "SECRET_KEY" not in out
    assert "key=<redacted>" in out
    assert "other=keep" in out


def test_sanitize_exception_message_http_error_redacts_token_query_param():
    pytest.importorskip("requests")
    import requests

    url = "https://api.example.com/v1/data?token=SECRET_TOKEN&other=keep"
    exc = requests.HTTPError(
        f"502 Bad Gateway for url: {url}",
        response=requests.Response(),
    )
    out = sanitize_exception_message(exc)
    assert "SECRET_TOKEN" not in out
    assert "token=<redacted>" in out
    assert "other=keep" in out


def test_sanitize_exception_message_redacts_authorization_bearer():
    exc = RuntimeError(
        "Slack request failed: Authorization: Bearer xoxb-1234-5678-ABCD"
    )
    out = sanitize_exception_message(exc)
    assert "xoxb-1234" not in out
    assert "Authorization: Bearer <redacted>" in out


def test_sanitize_exception_message_redacts_slack_xoxp_token():
    exc = RuntimeError("invalid token xoxp-long-token-value-here")
    out = sanitize_exception_message(exc)
    assert "long-token-value" not in out
    assert "xoxp-<redacted>" in out


def test_sanitize_exception_message_redacts_slack_xoxb_token():
    exc = RuntimeError("token xoxb-1234-5678-ABCD rejected")
    out = sanitize_exception_message(exc)
    assert "1234-5678" not in out
    assert "xoxb-<redacted>" in out


def test_sanitize_exception_message_redacts_url_userinfo():
    exc = RuntimeError(
        "clone failed: https://x-access-token:ghp_SECRET@github.com/o/r.git"
    )
    out = sanitize_exception_message(exc)
    assert "ghp_SECRET" not in out
    assert "https://<redacted>@github.com" in out


def test_sanitize_exception_message_unchanged_when_no_secrets():
    exc = RuntimeError("no secrets here")
    assert sanitize_exception_message(exc) == "no secrets here"


def test_handle_error_logs_redacted_exc_info_for_http_error():
    class PhaseCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "phase"

        def validate_config(self) -> None:
            return None

        def collect(self) -> GenericTrackerResult:
            return _OK

    exc = _http_error_with_secret_url()
    collector = PhaseCollector()
    collector._error_phase = "fetch"

    with patch.object(collector_lifecycle.logger, "exception") as mock_exc:
        collector.handle_error(exc)

    mock_exc.assert_called_once()
    exc_info = mock_exc.call_args.kwargs.get("exc_info")
    assert exc_info is not None
    assert exc_info is not True
    logged_exc = exc_info[1]
    logged_text = str(logged_exc)
    assert "SECRET_KEY" not in logged_text
    assert "key=<redacted>" in logged_text


class _TwoArgException(Exception):
    """Exception that cannot be reconstructed from a single sanitized message."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(code, message)

    def __str__(self) -> str:
        return self.message


def test_safe_exc_info_fallback_does_not_chain_unsanitized_cause():
    secret_url = "https://api.example.com/v1/data?key=SECRET_KEY"
    exc = _TwoArgException(500, f"request failed for url: {secret_url}")
    exc.__traceback__ = None

    exc_info = _safe_exc_info(exc)
    assert exc_info is not True
    assert isinstance(exc_info[1], RuntimeError)
    assert exc_info[1].__cause__ is None
    assert exc_info[1].__suppress_context__ is True

    formatted = "".join(traceback.format_exception(*exc_info))
    assert "SECRET_KEY" not in formatted
    assert "key=<redacted>" in formatted
    assert "The above exception was the direct cause" not in formatted


def test_handle_error_fallback_does_not_leak_secrets_in_exc_info():
    class PhaseCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "phase"

        def validate_config(self) -> None:
            return None

        def collect(self) -> GenericTrackerResult:
            return _OK

    secret_url = "https://api.example.com/v1/data?key=SECRET_KEY"
    exc = _TwoArgException(500, f"request failed for url: {secret_url}")
    collector = PhaseCollector()
    collector._error_phase = "fetch"

    with patch.object(collector_lifecycle.logger, "exception") as mock_exc:
        collector.handle_error(exc)

    exc_info = mock_exc.call_args.kwargs.get("exc_info")
    assert exc_info is not None
    assert exc_info is not True
    logged_exc = exc_info[1]
    assert logged_exc.__cause__ is None
    formatted = "".join(traceback.format_exception(*exc_info))
    assert "SECRET_KEY" not in formatted
    assert "key=<redacted>" in formatted
