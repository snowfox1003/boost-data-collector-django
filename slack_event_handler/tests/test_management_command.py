"""Tests for run_slack_event_handler management command."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_command_dry_run_validates_tokens(settings):
    settings.SLACK_BOT_TOKEN = {"T1": "xoxb-1"}
    cmd_mod = "slack_event_handler.management.commands.run_slack_event_handler"
    with patch(f"{cmd_mod}.logger") as log:
        with patch(f"{cmd_mod}.get_slack_bot_token", return_value="tok"):
            with patch(f"{cmd_mod}.get_slack_app_token", return_value="app"):
                call_command("run_slack_event_handler", "--dry-run", stdout=StringIO())
    assert log.info.called


@pytest.mark.django_db
def test_command_dry_run_warns_when_no_teams(settings):
    settings.SLACK_BOT_TOKEN = {}
    cmd_mod = "slack_event_handler.management.commands.run_slack_event_handler"
    with patch(f"{cmd_mod}.logger") as log:
        call_command("run_slack_event_handler", "--dry-run", stdout=StringIO())
    assert log.warning.called


@pytest.mark.django_db
def test_command_runs_runner(settings):
    settings.SLACK_BOT_TOKEN = {"T1": "x"}
    cmd_mod = "slack_event_handler.management.commands.run_slack_event_handler"
    with patch("slack_event_handler.runner.run_slack_event_handler") as run:
        with patch(f"{cmd_mod}.get_slack_bot_token", return_value="b"):
            with patch(f"{cmd_mod}.get_slack_app_token", return_value="a"):
                call_command("run_slack_event_handler", stdout=StringIO())
    run.assert_called_once()


@pytest.mark.django_db
def test_command_keyboard_interrupt_logs(settings):
    settings.SLACK_BOT_TOKEN = {"T1": "x"}
    cmd_mod = "slack_event_handler.management.commands.run_slack_event_handler"
    with patch(
        "slack_event_handler.runner.run_slack_event_handler",
        side_effect=KeyboardInterrupt,
    ):
        with patch(f"{cmd_mod}.logger") as log:
            with patch(f"{cmd_mod}.get_slack_bot_token", return_value="b"):
                with patch(f"{cmd_mod}.get_slack_app_token", return_value="a"):
                    call_command("run_slack_event_handler", stdout=StringIO())
    assert log.info.called
