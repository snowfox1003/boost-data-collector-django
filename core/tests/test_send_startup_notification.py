"""Tests for core.management.commands.send_startup_notification."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from celery.schedules import crontab
from celery.schedules import schedule as celery_interval_schedule

from django.core.management import call_command

from core.management.commands import send_startup_notification as ss

from core.management.commands.send_startup_notification import (
    collect_beat_lines,
    describe_celery_schedule,
    post_discord,
    post_slack,
)


def test_crontab_field_helpers():
    assert ss._crontab_field_to_sorted_ints(None) is None
    assert ss._crontab_field_to_sorted_ints(5) == [5]
    assert ss._crontab_field_to_sorted_ints({3, 1}) == [1, 3]
    assert ss._crontab_is_universal_star("*") is True
    assert ss._crontab_is_universal_star("mon") is False


def test_describe_unknown_schedule_uses_repr():
    assert "object" in ss.describe_celery_schedule(object()).lower() or repr(
        object()
    ) in ss.describe_celery_schedule(object())


def test_describe_interval_schedule():
    s = celery_interval_schedule(run_every=timedelta(minutes=30))
    assert "30" in describe_celery_schedule(s)


def test_describe_crontab_single_hour_minute():
    s = crontab(hour=9, minute=5)
    out = describe_celery_schedule(s)
    assert "09:05" in out


def test_describe_crontab_with_dow():
    s = crontab(hour=7, minute=0, day_of_week="mon-fri")
    out = describe_celery_schedule(s)
    assert "dow" in out.lower()


def test_collect_beat_lines_sorted():
    beat = {
        "z": {
            "task": "t.z",
            "schedule": celery_interval_schedule(run_every=timedelta(minutes=1)),
        },
        "a": {"task": "t.a", "schedule": None},
    }
    lines, total = collect_beat_lines(beat)
    assert total == 2
    assert lines[0].startswith("- `a`")


@patch("core.management.commands.send_startup_notification.request.urlopen")
def test_post_discord_warns_on_status(mock_urlopen):
    resp = MagicMock()
    resp.status = 500
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    mock_urlopen.return_value = resp
    post_discord("https://example.com/hook", "t", "d")
    mock_urlopen.assert_called_once()


@patch("core.management.commands.send_startup_notification.request.urlopen")
def test_post_slack_warns_on_non_200(mock_urlopen):
    resp = MagicMock()
    resp.status = 404
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    mock_urlopen.return_value = resp
    post_slack("https://example.com/hook", "t", "body")
    mock_urlopen.assert_called_once()


@pytest.mark.django_db
def test_command_skips_when_disabled(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = False
    call_command("send_startup_notification")


@pytest.mark.django_db
def test_command_skips_without_urls(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = ""
    settings.SLACK_WEBHOOK_URL = ""
    call_command("send_startup_notification")


@pytest.mark.django_db
def test_command_posts_discord_when_configured(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = "https://discord.example/x"
    settings.SLACK_WEBHOOK_URL = ""
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {}
    mock_app.control.inspect.return_value = None
    with patch(
        "core.management.commands.send_startup_notification.post_discord",
    ) as pd:
        with patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
        ):
            with patch(
                "core.management.commands.send_startup_notification.connection.introspection.table_names",
                return_value=["one"],
            ):
                with patch(
                    "core.management.commands.send_startup_notification.celery_app",
                    mock_app,
                ):
                    call_command("send_startup_notification")
    pd.assert_called_once()
