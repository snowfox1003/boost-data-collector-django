"""Tests for core.errors failure classification."""

import builtins
import errno
import importlib
import types

import pytest
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

from core.errors import CollectorFailureCategory, classify_failure

_swapped: dict[tuple[str, str], type[BaseException]] = {}


@pytest.fixture(autouse=True)
def _restore_swapped_exception_classes():
    yield
    for (module_name, attr_name), original in list(_swapped.items()):
        mod = importlib.import_module(module_name)
        setattr(mod, attr_name, original)
        del _swapped[(module_name, attr_name)]


def _swap_exc(module_name: str, attr_name: str, bases=(Exception,)):
    mod = importlib.import_module(module_name)
    key = (module_name, attr_name)
    if key not in _swapped:
        _swapped[key] = getattr(mod, attr_name)
    cls = types.new_class(attr_name, bases, exec_body=lambda ns: None)
    cls.__module__ = module_name
    setattr(mod, attr_name, cls)
    return cls


def _make_requests_exc(name: str, bases=(Exception,)):
    return _swap_exc("requests.exceptions", name, bases)


def _make_urllib3_exc(name: str):
    return _swap_exc("urllib3.exceptions", name)


def _make_httpx_exc(name: str):
    httpx = pytest.importorskip("httpx")

    exc_cls = getattr(httpx, name)
    mod_name = getattr(exc_cls, "__module__", "httpx")
    return _swap_exc(mod_name, name)


def test_classify_command_error():
    assert classify_failure(CommandError("bad")) is CollectorFailureCategory.COMMAND


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
    cls = _make_requests_exc(name)
    assert classify_failure(cls("x")) is category


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
    cls = _make_urllib3_exc(name)
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
    cls = _make_httpx_exc(name)
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
