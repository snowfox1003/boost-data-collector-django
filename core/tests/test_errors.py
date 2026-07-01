"""Tests for core.errors failure classification."""

import builtins
import errno

import pytest
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

from core.errors import (
    AuthenticationError,
    CollectorFailureCategory,
    CollectorValidationError,
    _classify_os_error,
    classify_failure,
)
from core.tests.failure_classification_helpers import (
    make_discord_exc,
    make_httpx_exc,
    make_requests_exc,
    make_slack_sdk_exc,
    make_urllib3_exc,
)


def test_classify_command_error():
    assert classify_failure(CommandError("bad")) is CollectorFailureCategory.COMMAND


def test_classify_authentication_error():
    assert (
        classify_failure(AuthenticationError("bad creds"))
        is CollectorFailureCategory.AUTH
    )


def test_classify_django_db_error_unknown():
    from django.db import OperationalError

    assert classify_failure(OperationalError("db")) is CollectorFailureCategory.UNKNOWN


def test_classify_discord_errors_module_429():
    cls = make_discord_exc("HTTPException")
    exc = cls("rate limited")
    exc.status = 429
    assert classify_failure(exc) is CollectorFailureCategory.RATE_LIMIT


def test_classify_discord_errors_module_unknown_without_status():
    cls = make_discord_exc("SomeOtherError")
    assert classify_failure(cls("x")) is CollectorFailureCategory.UNKNOWN


def test_classify_slack_sdk_errors_module_401():
    cls = make_slack_sdk_exc("SlackApiError")

    class Resp:
        status_code = 401

    exc = cls("auth")
    exc.response = Resp()
    assert classify_failure(exc) is CollectorFailureCategory.AUTH


def test_classify_validation_error():
    assert classify_failure(ValidationError("x")) is CollectorFailureCategory.VALIDATION


def test_classify_value_error():
    assert classify_failure(ValueError("x")) is CollectorFailureCategory.VALIDATION


def test_classify_permission_error():
    assert (
        classify_failure(PermissionError("no")) is CollectorFailureCategory.PERMISSION
    )


def test_classify_timeout_error():
    assert classify_failure(TimeoutError()) is CollectorFailureCategory.TIMEOUT


def test_classify_os_error_network_errno():
    assert (
        classify_failure(OSError(errno.EPIPE, "Broken pipe"))
        is CollectorFailureCategory.NETWORK
    )


def test_classify_os_error_direct_errno_network():
    assert (
        _classify_os_error(OSError(errno.ENOTCONN, "not connected"))
        is CollectorFailureCategory.NETWORK
    )


def test_classify_os_error_direct_winerror_network():
    exc = OSError(0, "wsa", None, 10061)
    assert _classify_os_error(exc) is CollectorFailureCategory.NETWORK


def test_classify_os_error_winerror_network_when_errno_not_in_sets():
    exc = OSError(999999, "generic message")
    exc.winerror = 10061
    assert classify_failure(exc) is CollectorFailureCategory.NETWORK


def test_classify_os_error_network_errno_connrefused():
    assert (
        classify_failure(OSError(errno.ECONNREFUSED, "refused"))
        is CollectorFailureCategory.NETWORK
    )


def test_classify_os_error_local_io_errno_unknown():
    assert (
        classify_failure(OSError(errno.ENOSPC, "no space"))
        is CollectorFailureCategory.UNKNOWN
    )


def test_classify_os_error_winerror_network():
    exc = OSError(0, "wsa", None, 10054)
    assert classify_failure(exc) is CollectorFailureCategory.NETWORK


def test_classify_os_error_connection_error_subclass():
    assert classify_failure(ConnectionResetError()) is CollectorFailureCategory.NETWORK


def test_classify_os_error_io_ambiguous_is_unknown():
    assert (
        classify_failure(OSError(errno.EIO, "Input/output error"))
        is CollectorFailureCategory.UNKNOWN
    )


def test_classify_os_error_filesystem_errno_unknown():
    assert (
        classify_failure(OSError(errno.ENOENT, "No such file"))
        is CollectorFailureCategory.UNKNOWN
    )


def test_classify_file_not_found_unknown():
    assert (
        classify_failure(FileNotFoundError("/no/such/path"))
        is CollectorFailureCategory.UNKNOWN
    )


def test_classify_unknown():
    assert classify_failure(RuntimeError("x")) is CollectorFailureCategory.UNKNOWN


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("HTTPError", CollectorFailureCategory.NETWORK),
        ("SSLError", CollectorFailureCategory.NETWORK),
        ("Timeout", CollectorFailureCategory.TIMEOUT),
        ("ReadTimeout", CollectorFailureCategory.TIMEOUT),
        ("ConnectTimeout", CollectorFailureCategory.TIMEOUT),
        ("ConnectionError", CollectorFailureCategory.NETWORK),
        ("ChunkedEncodingError", CollectorFailureCategory.NETWORK),
    ],
)
def test_classify_requests_exceptions(name, category):
    cls = make_requests_exc(name)
    assert classify_failure(cls("x")) is category


def _http_error_with_status(status_code: int | None):
    pytest.importorskip("requests")
    import requests

    exc = requests.HTTPError()
    if status_code is None:
        exc.response = None
    else:
        resp = requests.Response()
        resp.status_code = status_code
        exc.response = resp
    return exc


def test_classify_requests_http_error_429_rate_limit():
    assert (
        classify_failure(_http_error_with_status(429))
        is CollectorFailureCategory.RATE_LIMIT
    )


def test_classify_requests_http_error_401_auth():
    assert (
        classify_failure(_http_error_with_status(401)) is CollectorFailureCategory.AUTH
    )


def test_classify_requests_http_error_403_auth():
    assert (
        classify_failure(_http_error_with_status(403)) is CollectorFailureCategory.AUTH
    )


def test_classify_requests_http_error_other_status_network():
    assert (
        classify_failure(_http_error_with_status(500))
        is CollectorFailureCategory.NETWORK
    )


def test_classify_requests_http_error_no_response_network():
    assert (
        classify_failure(_http_error_with_status(None))
        is CollectorFailureCategory.NETWORK
    )


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("ReadTimeoutError", CollectorFailureCategory.TIMEOUT),
        ("ConnectTimeoutError", CollectorFailureCategory.TIMEOUT),
        ("TimeoutError", CollectorFailureCategory.TIMEOUT),
        ("ProtocolError", CollectorFailureCategory.NETWORK),
    ],
)
def test_classify_urllib3_exceptions(name, category):
    cls = make_urllib3_exc(name)
    assert classify_failure(cls("x")) is category


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("ReadTimeout", CollectorFailureCategory.TIMEOUT),
        ("HTTPStatusError", CollectorFailureCategory.NETWORK),
        ("TransportError", CollectorFailureCategory.NETWORK),
        ("ConnectError", CollectorFailureCategory.NETWORK),
    ],
)
def test_classify_httpx(name, category):
    cls = make_httpx_exc(name)
    assert classify_failure(cls("x")) is category


def test_classify_validation_error_when_django_exceptions_import_fails(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "django.core.exceptions":
            raise ImportError("blocked")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert classify_failure(ValidationError("x")) is CollectorFailureCategory.UNKNOWN


def test_classify_command_error_when_management_import_fails(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "django.core.management.base":
            raise ImportError("blocked")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert classify_failure(CommandError("x")) is CollectorFailureCategory.UNKNOWN


def test_classify_pydantic_validation_error():
    pydantic = pytest.importorskip("pydantic")
    from pydantic import BaseModel

    class M(BaseModel):
        x: int

    try:
        M.model_validate({"x": "not-int"})
    except pydantic.ValidationError as exc:
        assert classify_failure(exc) is CollectorFailureCategory.VALIDATION
    else:
        pytest.fail("expected ValidationError")


def test_classify_github_api_validation_error():
    from github_activity_tracker.api_schemas import GitHubApiValidationError

    assert (
        classify_failure(GitHubApiValidationError("bad issue"))
        is CollectorFailureCategory.VALIDATION
    )


def test_classify_slack_api_validation_error():
    from cppa_slack_tracker.api_schemas import SlackApiValidationError

    assert (
        classify_failure(SlackApiValidationError("bad slack"))
        is CollectorFailureCategory.VALIDATION
    )


def test_classify_collector_validation_error_unchanged_when_module_moved():
    class MovedError(CollectorValidationError):
        pass

    MovedError.__module__ = "totally.unrelated.module.path"
    assert classify_failure(MovedError("bad")) is CollectorFailureCategory.VALIDATION


def test_classify_authentication_error_unchanged_when_module_moved():
    class MovedAuth(AuthenticationError):
        pass

    MovedAuth.__module__ = "renamed.apps.auth"
    assert classify_failure(MovedAuth("x")) is CollectorFailureCategory.AUTH
