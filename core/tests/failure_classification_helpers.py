"""Shared helpers for failure-classification tests."""

from __future__ import annotations

import importlib
import sys
import types

import pytest

_swapped: dict[tuple[str, str], type[BaseException]] = {}


@pytest.fixture(autouse=True)
def _restore_swapped_exception_classes():
    yield
    for (module_name, attr_name), original in list(_swapped.items()):
        mod = importlib.import_module(module_name)
        if original is None:
            if hasattr(mod, attr_name):
                delattr(mod, attr_name)
        else:
            setattr(mod, attr_name, original)
        del _swapped[(module_name, attr_name)]


def ensure_module(module_name: str, *, parent: str | None = None) -> None:
    """Register a stub module in ``sys.modules`` when an optional SDK is absent."""
    if module_name in sys.modules:
        return
    short_name = module_name.rsplit(".", 1)[-1]
    child = types.ModuleType(short_name)
    child.__package__ = module_name
    sys.modules[module_name] = child
    if parent is not None:
        if parent not in sys.modules:
            sys.modules[parent] = types.ModuleType(parent)
        setattr(sys.modules[parent], short_name, child)


def ensure_discord_errors_module() -> None:
    try:
        importlib.import_module("discord.errors")
    except ImportError:
        ensure_module("discord.errors", parent="discord")


def swap_exc(
    module_name: str, attr_name: str, bases=(Exception,)
) -> type[BaseException]:
    mod = importlib.import_module(module_name)
    key = (module_name, attr_name)
    if key not in _swapped:
        _swapped[key] = getattr(mod, attr_name, None)
    cls = types.new_class(attr_name, bases, exec_body=lambda ns: None)
    cls.__module__ = module_name
    setattr(mod, attr_name, cls)
    return cls


def make_requests_exc(name: str, bases=(Exception,)) -> type[BaseException]:
    return swap_exc("requests.exceptions", name, bases)


def make_urllib3_exc(name: str) -> type[BaseException]:
    return swap_exc("urllib3.exceptions", name)


def make_httpx_exc(name: str) -> type[BaseException]:
    httpx = pytest.importorskip("httpx")

    exc_cls = getattr(httpx, name)
    mod_name = getattr(exc_cls, "__module__", "httpx")
    return swap_exc(mod_name, name)


def make_discord_exc(name: str, bases=(Exception,)) -> type[BaseException]:
    ensure_discord_errors_module()
    return swap_exc("discord.errors", name, bases)


def make_slack_sdk_exc(name: str, bases=(Exception,)) -> type[BaseException]:
    try:
        importlib.import_module("slack_sdk.errors")
    except ImportError:
        ensure_module("slack_sdk.errors", parent="slack_sdk")
    return swap_exc("slack_sdk.errors", name, bases)
