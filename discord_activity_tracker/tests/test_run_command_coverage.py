"""Coverage for run_discord_activity_tracker command _handle_core and helpers."""

from __future__ import annotations

import asyncio
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError

from discord_activity_tracker.management.commands.run_discord_activity_tracker import (
    Command,
    DiscordActivityCollector,
    _resolve_exporter_date_bounds,
    task_preprocess_workspace,
)


def _cmd_collector(**opts):
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
    cmd.style.WARNING = lambda x: x
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options=defaults)
    return cmd, collector


@pytest.mark.django_db
def test_resolve_bounds_since_after_until_resets(monkeypatch, caplog):
    """since > until logs warning and falls back so bounds are recomputed."""
    caplog.set_level("WARNING")
    after, before, _per_ch = _resolve_exporter_date_bounds(
        {"since": "2026-06-10", "until": "2026-06-01"},
        guild_snowflake=1,
        channel_ids=[],
    )
    assert before is None
    assert after is None
    assert "invalid date range" in caplog.text


def test_resolve_bounds_bad_since_raises_command_error():
    with pytest.raises(CommandError):
        _resolve_exporter_date_bounds(
            {"since": "not-a-date", "until": None},
            guild_snowflake=1,
            channel_ids=[],
        )


@pytest.mark.django_db
def test_handle_core_dry_run_all_branches(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9001)
    _, collector = _cmd_collector(
        dry_run=True,
        skip_discord_sync=False,
        skip_markdown_export=False,
        skip_remote_push=False,
        skip_pinecone=False,
        since="2026-01-01",
        until="2026-01-31",
    )
    with patch(
        "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_preprocess_workspace"
    ) as tp:
        collector.cmd._handle_core(collector.options, collector)
    tp.assert_called_once_with(dry_run=True)
    out = collector.stdout.getvalue()
    assert "DRY RUN" in out
    assert "Lower bound" in out
    assert "Upper bound" in out


@pytest.mark.django_db
def test_handle_core_dry_run_skip_sync_only(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9002)
    _, collector = _cmd_collector(
        dry_run=True,
        skip_discord_sync=True,
        skip_markdown_export=True,
        skip_remote_push=True,
        skip_pinecone=True,
    )
    with patch(
        "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_preprocess_workspace"
    ):
        collector.cmd._handle_core(collector.options, collector)
    out = collector.stdout.getvalue()
    assert "today" in out.lower()


@pytest.mark.django_db
def test_handle_core_task_sync_skips_markdown(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9003)
    _, collector = _cmd_collector(dry_run=False, task="sync")
    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_sync"
        ) as ts,
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_markdown_export_and_push"
        ) as tm,
    ):
        collector.cmd._handle_core(collector.options, collector)
    ts.assert_called_once()
    tm.assert_called_once()
    assert collector.options["skip_markdown_export"] is True
    assert collector.options["skip_remote_push"] is True


@pytest.mark.django_db
def test_handle_core_task_export_skips_sync(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9004)
    _, collector = _cmd_collector(dry_run=False, task="export")
    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_sync"
        ) as ts,
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_markdown_export_and_push"
        ) as tm,
    ):
        collector.cmd._handle_core(collector.options, collector)
    ts.assert_called_once()
    tm.assert_called_once()
    assert collector.options["skip_discord_sync"] is True
    assert collector.options["skip_pinecone"] is True


@pytest.mark.django_db
def test_handle_core_non_dry_calls_sync_and_markdown(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9005)
    _, collector = _cmd_collector(dry_run=False)
    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_sync"
        ) as ts,
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_markdown_export_and_push"
        ) as tm,
    ):
        collector.cmd._handle_core(collector.options, collector)
    ts.assert_called_once()
    tm.assert_called_once()


@pytest.mark.django_db
def test_handle_core_skip_pinecone_logs(monkeypatch, settings, caplog):
    caplog.set_level("INFO")
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9006)
    _, collector = _cmd_collector(dry_run=False, skip_pinecone=True)
    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_sync"
        ) as ts,
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_markdown_export_and_push"
        ) as tm,
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_pinecone_sync"
        ) as tp,
    ):
        collector.cmd._handle_core(collector.options, collector)
        collector.sync_pinecone()
    ts.assert_called_once()
    tm.assert_called_once()
    tp.assert_not_called()
    assert "skipping Pinecone (--skip-pinecone)" in caplog.text


@pytest.mark.django_db
def test_handle_core_propagates_task_failure(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9007)
    _, collector = _cmd_collector(dry_run=False)
    with patch(
        "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_sync",
        side_effect=RuntimeError("fail"),
    ):
        with pytest.raises(RuntimeError, match="fail"):
            collector.cmd._handle_core(collector.options, collector)


def test_get_collector_normalizes_skip_pinecone_none():
    cmd = Command()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    c = cmd.get_collector(
        dry_run=False,
        skip_discord_sync=False,
        skip_markdown_export=False,
        skip_remote_push=False,
        skip_pinecone=None,
    )
    assert c.options.get("skip_pinecone") is False


@pytest.mark.django_db
def test_task_preprocess_workspace_dry_run(tmp_path, settings):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    task_preprocess_workspace(dry_run=True)


def test_resolve_bounds_since_naive_becomes_utc():
    after, before, _per_ch = _resolve_exporter_date_bounds(
        {"since": "2026-04-01T00:00:00", "until": None},
        guild_snowflake=1,
        channel_ids=[],
    )
    assert after is not None
    assert after.tzinfo is not None
    assert before is None


@pytest.mark.django_db
def test_handle_core_task_all_runs_both_phases(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9008)
    _, collector = _cmd_collector(dry_run=False, task="all")
    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_sync"
        ) as ts,
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_markdown_export_and_push"
        ) as tm,
    ):
        collector.cmd._handle_core(collector.options, collector)
    ts.assert_called_once()
    tm.assert_called_once()


@pytest.mark.django_db
def test_handle_core_wraps_discord_exporter_error(monkeypatch, settings):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "tok")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9009)
    _, collector = _cmd_collector(dry_run=False)
    with patch(
        "discord_activity_tracker.management.commands.run_discord_activity_tracker.task_discord_sync",
        side_effect=CommandError("DiscordChatExporter failed: cli missing"),
    ):
        with pytest.raises(CommandError, match="DiscordChatExporter"):
            collector.cmd._handle_core(collector.options, collector)


@pytest.mark.django_db
def test_persist_channel_inserts_messages(monkeypatch, settings, tmp_path):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    gid, cid = 330011, 330022
    guild_info = {"id": gid, "name": "Guild", "iconUrl": ""}
    channel_info = {
        "id": cid,
        "name": "chan",
        "type": "GuildTextChat",
        "topic": "",
        "category": "",
        "categoryId": None,
    }
    messages = [
        {
            "id": str(10**12 + 7),
            "type": "Default",
            "isPinned": False,
            "timestamp": "2026-01-15T12:00:00Z",
            "content": "hello world example text long enough for validation",
            "author": {"id": "1082347485026070548", "name": "user"},
            "attachments": [],
            "reactions": [],
        }
    ]
    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    collector = DiscordActivityCollector(cmd=cmd, options={})
    count = asyncio.run(collector._persist_channel(guild_info, channel_info, messages))
    assert count >= 1
