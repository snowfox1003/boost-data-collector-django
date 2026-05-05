"""Tests for slack_event_handler.runner."""

from unittest.mock import MagicMock, patch

import pytest

from slack_event_handler.runner import run_slack_event_handler


@pytest.mark.django_db
def test_run_slack_event_handler_no_teams_logs_error(settings, tmp_path):
    settings.SLACK_BOT_TOKEN = {}
    ws = str(tmp_path / "slack-ws")
    with patch("slack_event_handler.runner.get_workspace_root", return_value=ws):
        with patch("slack_event_handler.runner.logger") as log:
            run_slack_event_handler()
    log.error.assert_called()


@pytest.mark.django_db
def test_run_slack_event_handler_workspace_root_failure_still_runs(settings):
    settings.SLACK_BOT_TOKEN = {}
    with patch(
        "slack_event_handler.runner.get_workspace_root",
        side_effect=OSError("no workspace"),
    ):
        with patch("slack_event_handler.runner.logger") as log:
            run_slack_event_handler()
    log.exception.assert_called()
    log.error.assert_called()


@pytest.mark.django_db
def test_run_slack_event_handler_workspace_root_type_error_still_runs(settings):
    settings.SLACK_BOT_TOKEN = {}
    with patch(
        "slack_event_handler.runner.get_workspace_root",
        side_effect=TypeError("bad WORKSPACE_DIR type"),
    ):
        with patch("slack_event_handler.runner.logger") as log:
            run_slack_event_handler()
    log.exception.assert_called()
    log.error.assert_called()


@pytest.mark.django_db
def test_run_slack_event_handler_starts_listener_threads(
    settings, tmp_path, fake_slack_bolt
):
    pytest.importorskip("github")
    settings.SLACK_BOT_TOKEN = {"T123": "xoxb-test-token"}
    mock_thread = MagicMock()
    ws = str(tmp_path / "ws")
    with patch("slack_event_handler.runner.get_workspace_root", return_value=ws):
        with patch(
            "slack_event_handler.runner.get_slack_app_token",
            return_value="xapp-test",
        ):
            with patch(
                "slack_event_handler.runner.threading.Thread",
                return_value=mock_thread,
            ) as mock_thread_cls:
                run_slack_event_handler()
    mock_thread_cls.assert_called_once()
    mock_thread.start.assert_called_once()
    mock_thread.join.assert_called_once()


@pytest.mark.django_db
def test_run_slack_event_handler_non_dict_tokens_treated_as_empty(settings, tmp_path):
    settings.SLACK_BOT_TOKEN = "not-a-dict"
    with patch(
        "slack_event_handler.runner.get_workspace_root", return_value=str(tmp_path)
    ):
        with patch("slack_event_handler.runner.logger") as log:
            run_slack_event_handler()
    log.error.assert_called()


@pytest.mark.django_db
def test_run_slack_event_handler_skips_empty_bot_token(
    settings, tmp_path, fake_slack_bolt
):
    settings.SLACK_BOT_TOKEN = {"T1": "  "}
    with patch(
        "slack_event_handler.runner.get_workspace_root", return_value=str(tmp_path)
    ):
        with patch("slack_event_handler.runner.logger") as log:
            run_slack_event_handler()
    log.error.assert_called()


@pytest.mark.django_db
def test_run_slack_event_handler_skips_when_app_token_missing(
    settings, tmp_path, fake_slack_bolt
):
    settings.SLACK_BOT_TOKEN = {"T9": "xoxb-valid-token"}
    with patch(
        "slack_event_handler.runner.get_workspace_root", return_value=str(tmp_path)
    ):
        with patch(
            "slack_event_handler.runner.get_slack_app_token",
            side_effect=ValueError("missing"),
        ):
            with patch("slack_event_handler.runner.logger") as log:
                run_slack_event_handler()
    assert log.warning.called


@pytest.mark.django_db
def test_run_slack_event_handler_two_teams_start_two_threads(
    settings, tmp_path, fake_slack_bolt
):
    settings.SLACK_BOT_TOKEN = {"TA": "xoxb-a", "TB": "xoxb-b"}
    mock_thread = MagicMock()
    with patch(
        "slack_event_handler.runner.get_workspace_root", return_value=str(tmp_path)
    ):
        with patch(
            "slack_event_handler.runner.get_slack_app_token",
            side_effect=["app-a", "app-b"],
        ):
            with patch(
                "slack_event_handler.runner.threading.Thread",
                return_value=mock_thread,
            ) as mock_tc:
                run_slack_event_handler()
    assert mock_tc.call_count == 2
    assert mock_thread.start.call_count == 2
