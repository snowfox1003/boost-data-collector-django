"""Slack event handler test fixtures."""

import sys
from types import ModuleType
from unittest.mock import patch

import pytest


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
