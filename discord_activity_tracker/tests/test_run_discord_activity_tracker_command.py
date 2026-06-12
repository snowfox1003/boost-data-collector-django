"""Tests for run_discord_activity_tracker management command."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from discord_activity_tracker.management.commands.run_discord_activity_tracker import (
    Command,
    DiscordActivityCollector,
    _parse_channel_ids,
    _resolve_exporter_date_bounds,
)
from discord_activity_tracker.staging_schema import StagingValidationError


def _cmd_and_collector(**opts):
    defaults = {
        "dry_run": False,
        "skip_discord_sync": False,
        "skip_markdown_export": False,
        "skip_remote_push": False,
        "skip_pinecone": False,
        "channels": "",
        "since": None,
        "until": None,
        "task": None,
    }
    defaults.update(opts)
    cmd = Command()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    collector = DiscordActivityCollector(cmd=cmd, options=defaults)
    collector.style.SUCCESS = lambda x: x
    collector.style.WARNING = lambda x: x
    return cmd, collector


def test_staging_validation_error_subclasses_value_error():
    assert issubclass(StagingValidationError, ValueError)


# ---------------------------------------------------------------------------
# _parse_channel_ids
# ---------------------------------------------------------------------------


def test_parse_channel_ids_basic():
    assert _parse_channel_ids("1,2,3") == [1, 2, 3]


def test_parse_channel_ids_strips_whitespace():
    assert _parse_channel_ids(" 10 , 20 ") == [10, 20]


def test_parse_channel_ids_skips_non_digits():
    assert _parse_channel_ids("abc,123,!@#") == [123]


def test_parse_channel_ids_empty_string():
    assert _parse_channel_ids("") == []


# ---------------------------------------------------------------------------
# _resolve_exporter_date_bounds
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_bounds_no_since_empty_db_after_is_none(settings):
    settings.USE_TZ = True
    after, before, per_ch = _resolve_exporter_date_bounds(
        {"since": None, "until": None},
        guild_snowflake=888001,
        channel_ids=[],
    )
    assert before is None
    assert after is None
    assert per_ch is True


def test_resolve_bounds_since_until_only():
    after, before, per_ch = _resolve_exporter_date_bounds(
        {
            "since": "2026-01-01",
            "until": "2026-01-31",
        },
        guild_snowflake=1,
        channel_ids=[],
    )
    assert after is not None and before is not None
    assert per_ch is False


def test_resolve_bounds_explicit_since_no_until():
    after, before, per_ch = _resolve_exporter_date_bounds(
        {"since": "2026-05-01", "until": None},
        guild_snowflake=1,
        channel_ids=[],
    )
    assert after is not None
    assert before is None
    assert per_ch is False


@pytest.mark.django_db
def test_resolve_bounds_no_since_uses_latest_db_message():
    from datetime import datetime, timezone

    from cppa_user_tracker.models import DiscordProfile
    from discord_activity_tracker.models import (
        DiscordChannel,
        DiscordMessage,
        DiscordServer,
    )

    server = DiscordServer.objects.create(server_id=700, server_name="S", icon_url="")
    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=701,
        channel_name="c",
        channel_type="text",
    )
    author = DiscordProfile.objects.create(
        discord_user_id=701001,
        username="u",
        display_name="U",
        avatar_url="",
        is_bot=False,
    )
    msg_time = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)
    DiscordMessage.objects.create(
        message_id=701002,
        channel=ch,
        author=author,
        content="hello world example text long enough",
        message_created_at=msg_time,
    )

    after, before, per_ch = _resolve_exporter_date_bounds(
        {"since": None, "until": None},
        guild_snowflake=700,
        channel_ids=[701],
    )
    assert before is None
    assert after == msg_time
    assert per_ch is True


# ---------------------------------------------------------------------------
# Channel allowlist from settings vs --channels override
# ---------------------------------------------------------------------------


def test_collector_uses_settings_channel_ids(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_CHANNEL_IDS", [111, 222])
    _, c = _cmd_and_collector()
    assert c.channel_ids == [111, 222]


def test_collector_channels_arg_overrides_settings(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_CHANNEL_IDS", [111, 222])
    _, c = _cmd_and_collector(channels="333,444")
    assert c.channel_ids == [333, 444]


def test_collector_empty_channels_arg_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_CHANNEL_IDS", [555])
    _, c = _cmd_and_collector(channels="")
    assert c.channel_ids == [555]


# ---------------------------------------------------------------------------
# Missing credentials validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_handle_core_raises_when_user_token_missing(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "")
    monkeypatch.setattr(settings, "ALLOW_INTERNAL_DISCORD_TOKENS", False)
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9999)
    cmd, collector = _cmd_and_collector()
    with pytest.raises(CommandError, match="Discord credentials not configured"):
        cmd._handle_core(collector.options, collector=collector)


@pytest.mark.django_db
def test_handle_core_raises_when_server_id_missing(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", None)
    cmd, collector = _cmd_and_collector()
    with pytest.raises(CommandError, match="DISCORD_SERVER_ID"):
        cmd._handle_core(collector.options, collector=collector)


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dry_run_prints_config(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9999)
    monkeypatch.setattr(settings, "DISCORD_CHANNEL_IDS", [1, 2, 3])
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        dry_run=True,
        stdout=out,
        verbosity=0,
    )
    assert "DRY RUN" in out.getvalue()


# ---------------------------------------------------------------------------
# sync_pinecone skipped with --skip-pinecone / --ignore-pinecone
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sync_pinecone_skipped_when_skip_flag(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9999)
    _, c = _cmd_and_collector(skip_pinecone=True, dry_run=True)
    c.sync_pinecone()


@pytest.mark.django_db
def test_sync_pinecone_skipped_when_dry_run(monkeypatch):
    _, c = _cmd_and_collector(dry_run=True)
    c.sync_pinecone()


@pytest.mark.django_db
def test_sync_pinecone_calls_run_cppa_pinecone_sync(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9999)
    monkeypatch.setattr(settings, "PINECONE_DISCORD_APP_TYPE", "discord")
    monkeypatch.setattr(settings, "PINECONE_DISCORD_NAMESPACE", "discord-messages")
    _, c = _cmd_and_collector(skip_pinecone=False, dry_run=False)
    with patch(
        "discord_activity_tracker.pinecone_runner.call_command",
    ) as cc:
        c.sync_pinecone()
    cc.assert_called_once()
    assert cc.call_args[0][0] == "run_cppa_pinecone_sync"


@pytest.mark.django_db
def test_sync_pinecone_skipped_when_app_type_empty(monkeypatch):
    monkeypatch.setattr(settings, "PINECONE_DISCORD_APP_TYPE", "")
    monkeypatch.setattr(settings, "PINECONE_DISCORD_NAMESPACE", "ns")
    _, c = _cmd_and_collector(skip_pinecone=False, dry_run=False)
    with patch("discord_activity_tracker.pinecone_runner.call_command") as cc:
        c.sync_pinecone()
    cc.assert_not_called()


# ---------------------------------------------------------------------------
# DISCORD_SERVER_ID is already int from settings
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_server_id_is_already_int_in_settings(monkeypatch):
    """Large snowflake as int for DISCORD_SERVER_ID must not break _handle_core."""
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 331718482485837825)
    cmd, collector = _cmd_and_collector(dry_run=True)
    cmd._handle_core(collector.options, collector=collector)


# ---------------------------------------------------------------------------
# command get_collector wiring
# ---------------------------------------------------------------------------


def test_get_collector_returns_discord_activity_collector():
    cmd = Command()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    collector = cmd.get_collector(
        dry_run=True,
        channels="999",
        skip_pinecone=True,
        skip_discord_sync=False,
        skip_markdown_export=False,
        skip_remote_push=False,
        since=None,
        until=None,
        task=None,
    )
    assert isinstance(collector, DiscordActivityCollector)
    assert collector.options["dry_run"] is True
    assert collector.channel_ids == [999]
