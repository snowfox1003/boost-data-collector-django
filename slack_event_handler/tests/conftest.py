"""Slack event handler test fixtures."""

import sys
from types import ModuleType
from unittest.mock import patch

import pytest


class ImmediateThread:
    """Drop-in threading.Thread replacement that runs target synchronously on start()."""

    def __init__(
        self,
        group=None,
        target=None,
        name=None,
        args=(),
        kwargs=None,
        *,
        daemon=None,
    ):
        self._target = target
        self._args = args

    def start(self):
        if self._target:
            self._target(*self._args)


@pytest.fixture
def fake_slack_bolt():
    """Minimal slack_bolt package in sys.modules so slack_listener can import."""
    for key in list(sys.modules):
        if key == "slack_event_handler.utils.slack_listener" or key.startswith(
            "slack_event_handler.utils.slack_listener."
        ):
            sys.modules.pop(key, None)

    socket_mode = ModuleType("slack_bolt.adapter.socket_mode")
    adapter = ModuleType("slack_bolt.adapter")
    bolt = ModuleType("slack_bolt")

    class _DummyApp:
        def __init__(self, *args, **kwargs):
            pass

    socket_mode.SocketModeHandler = lambda *a, **k: None
    adapter.socket_mode = socket_mode
    bolt.App = _DummyApp

    with patch.dict(
        sys.modules,
        {
            "slack_bolt": bolt,
            "slack_bolt.adapter": adapter,
            "slack_bolt.adapter.socket_mode": socket_mode,
        },
    ):
        yield
