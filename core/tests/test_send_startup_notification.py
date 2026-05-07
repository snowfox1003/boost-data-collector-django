"""Tests for core.management.commands.send_startup_notification."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from celery.schedules import crontab
from celery.schedules import schedule as celery_interval_schedule

from django.core.management import call_command
from urllib.error import URLError

from core.management.commands import send_startup_notification as ss

from core.management.commands.send_startup_notification import (
    BEAT_LINES_CAP,
    collect_beat_lines,
    describe_celery_schedule,
    post_discord,
    post_slack,
)


def test_crontab_field_helpers():
    assert ss._crontab_field_to_sorted_ints(None) is None
    assert ss._crontab_field_to_sorted_ints(5) == [5]
    assert ss._crontab_field_to_sorted_ints({3, 1}) == [1, 3]
    assert ss._crontab_field_to_sorted_ints([1, "2", 3]) == [1, 2, 3]
    assert ss._crontab_field_to_sorted_ints(["x"]) is None
    assert ss._crontab_field_to_sorted_ints("not-a-crontab-field") is None
    assert ss._crontab_is_universal_star(None) is True
    assert ss._crontab_is_universal_star("*") is True
    assert ss._crontab_is_universal_star("**") is True
    assert ss._crontab_is_universal_star("mon") is False


def test_describe_unknown_schedule_uses_repr():
    assert "object" in ss.describe_celery_schedule(object()).lower() or repr(
        object()
    ) in ss.describe_celery_schedule(object())


def test_describe_interval_schedule():
    s = celery_interval_schedule(run_every=timedelta(minutes=30))
    assert "30" in describe_celery_schedule(s)


def test_describe_crontab_multi_hour_minute_uses_repr():
    s = crontab(hour={0, 12}, minute={0, 30})
    out = describe_celery_schedule(s)
    assert "hour=" in out or "minute=" in out


def test_describe_crontab_includes_dom_and_moy_when_set():
    s = crontab(hour=1, minute=0, day_of_month="1", month_of_year="1")
    out = describe_celery_schedule(s)
    assert "dom=" in out
    assert "moy=" in out


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


def test_collect_beat_lines_truncation_hint_in_command_body():
    """BEAT_LINES_CAP limits lines; remainder is summarized when building body."""
    beat = {
        f"k{i}": {"task": f"t{i}", "schedule": None} for i in range(BEAT_LINES_CAP + 3)
    }
    lines, total = collect_beat_lines(beat)
    assert total == BEAT_LINES_CAP + 3
    assert len(lines) == BEAT_LINES_CAP + 3
    shown = lines[:BEAT_LINES_CAP]
    beat_block = "\n".join(shown)
    if total > len(shown):
        beat_block += f"\n… and {total - len(shown)} more"
    assert "… and 3 more" in beat_block


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


@pytest.mark.django_db
def test_command_db_failure_still_posts(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = "https://discord.example/x"
    settings.SLACK_WEBHOOK_URL = ""
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {}
    mock_app.control.inspect.return_value = None
    with (
        patch(
            "core.management.commands.send_startup_notification.post_discord",
        ) as pd,
        patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
            side_effect=RuntimeError("db down"),
        ),
        patch(
            "core.management.commands.send_startup_notification.celery_app",
            mock_app,
        ),
    ):
        call_command("send_startup_notification")
    args = pd.call_args[0]
    assert "DB: failed" in args[2]


@pytest.mark.django_db
def test_command_worker_inspect_failure(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = "https://discord.example/x"
    settings.SLACK_WEBHOOK_URL = ""
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {}
    mock_app.control.inspect.side_effect = RuntimeError("no broker")
    with (
        patch(
            "core.management.commands.send_startup_notification.post_discord",
        ) as pd,
        patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.introspection.table_names",
            return_value=[],
        ),
        patch(
            "core.management.commands.send_startup_notification.celery_app",
            mock_app,
        ),
    ):
        call_command("send_startup_notification")
    body = pd.call_args[0][2]
    assert "inspect failed" in body


@pytest.mark.django_db
def test_command_exits_on_webhook_error(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = "https://discord.example/x"
    settings.SLACK_WEBHOOK_URL = ""
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {}
    mock_app.control.inspect.return_value = None
    with (
        patch(
            "core.management.commands.send_startup_notification.post_discord",
            side_effect=URLError("bad"),
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.introspection.table_names",
            return_value=["t"],
        ),
        patch(
            "core.management.commands.send_startup_notification.celery_app",
            mock_app,
        ),
    ):
        with pytest.raises(SystemExit) as excinfo:
            call_command("send_startup_notification")
    assert excinfo.value.code == 1


@pytest.mark.django_db
def test_command_beat_block_truncation_in_notification_body(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = "https://discord.example/x"
    settings.SLACK_WEBHOOK_URL = ""
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {
        f"k{i}": {"task": f"t{i}", "schedule": None} for i in range(BEAT_LINES_CAP + 4)
    }
    mock_app.control.inspect.return_value = None
    with (
        patch(
            "core.management.commands.send_startup_notification.post_discord",
        ) as pd,
        patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.introspection.table_names",
            return_value=["t"],
        ),
        patch(
            "core.management.commands.send_startup_notification.celery_app",
            mock_app,
        ),
    ):
        call_command("send_startup_notification")
    body = pd.call_args[0][2]
    assert "… and 4 more" in body


@pytest.mark.django_db
def test_command_generic_exception_from_discord(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = "https://discord.example/x"
    settings.SLACK_WEBHOOK_URL = ""
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {}
    mock_app.control.inspect.return_value = None
    with (
        patch(
            "core.management.commands.send_startup_notification.post_discord",
            side_effect=ValueError("boom"),
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.introspection.table_names",
            return_value=["t"],
        ),
        patch(
            "core.management.commands.send_startup_notification.celery_app",
            mock_app,
        ),
    ):
        with pytest.raises(SystemExit):
            call_command("send_startup_notification")


@pytest.mark.django_db
def test_command_slack_webhook_urllib_error_exits(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = ""
    settings.SLACK_WEBHOOK_URL = "https://hooks.slack.example/x"
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {}
    mock_app.control.inspect.return_value = None
    with (
        patch(
            "core.management.commands.send_startup_notification.post_slack",
            side_effect=URLError("slack down"),
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.introspection.table_names",
            return_value=["t"],
        ),
        patch(
            "core.management.commands.send_startup_notification.celery_app",
            mock_app,
        ),
    ):
        with pytest.raises(SystemExit) as exc:
            call_command("send_startup_notification")
    assert exc.value.code == 1


@pytest.mark.django_db
def test_command_slack_webhook_generic_exception_exits(settings):
    settings.ENABLE_STARTUP_NOTIFICATIONS = True
    settings.DISCORD_WEBHOOK_URL = ""
    settings.SLACK_WEBHOOK_URL = "https://hooks.slack.example/x"
    mock_app = MagicMock()
    mock_app.conf.beat_schedule = {}
    mock_app.control.inspect.return_value = None
    with (
        patch(
            "core.management.commands.send_startup_notification.post_slack",
            side_effect=RuntimeError("slack boom"),
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.ensure_connection",
        ),
        patch(
            "core.management.commands.send_startup_notification.connection.introspection.table_names",
            return_value=["t"],
        ),
        patch(
            "core.management.commands.send_startup_notification.celery_app",
            mock_app,
        ),
    ):
        with pytest.raises(SystemExit) as exc:
            call_command("send_startup_notification")
    assert exc.value.code == 1
