"""Tests for slack_event_handler.apps."""

from __future__ import annotations

from importlib import import_module
from unittest.mock import MagicMock, patch

from slack_event_handler.apps import SlackEventHandlerConfig


def _config() -> SlackEventHandlerConfig:
    mod = import_module("slack_event_handler")
    return SlackEventHandlerConfig("slack_event_handler", mod)


def test_ready_returns_early_when_not_runserver():
    cfg = _config()
    with patch("slack_event_handler.apps.sys.argv", ["manage.py", "migrate"]):
        cfg.ready()


def test_ready_returns_early_when_run_main_not_true(monkeypatch):
    monkeypatch.delenv("RUN_MAIN", raising=False)
    cfg = _config()
    with patch("slack_event_handler.apps.sys.argv", ["manage.py", "runserver"]):
        cfg.ready()


def test_ready_starts_daemon_thread_when_runserver_child(monkeypatch):
    monkeypatch.setenv("RUN_MAIN", "true")
    cfg = _config()
    mock_thread = MagicMock()
    with patch("slack_event_handler.apps.sys.argv", ["manage.py", "runserver"]):
        with patch(
            "slack_event_handler.apps.threading.Thread", return_value=mock_thread
        ) as mock_tc:
            cfg.ready()
    mock_tc.assert_called_once()
    assert mock_tc.call_args.kwargs["daemon"] is True
    assert mock_tc.call_args.kwargs["name"] == "slack-event-handler"
    mock_thread.start.assert_called_once()

    inner_target = mock_tc.call_args.kwargs["target"]
    with patch("slack_event_handler.runner.run_slack_event_handler") as run_handler:
        inner_target()
    run_handler.assert_called_once()
