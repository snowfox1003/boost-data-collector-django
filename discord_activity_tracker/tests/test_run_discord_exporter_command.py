"""Tests for run_discord_exporter management command and DiscordExporterCollector."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone as django_timezone

from discord_activity_tracker.management.commands.run_discord_exporter import (
    Command as ExporterCommand,
    DiscordExporterCollector,
)
from discord_activity_tracker.models import DiscordChannel, DiscordServer


@pytest.fixture
def discord_exporter_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", "user-token")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", "4242")
    monkeypatch.setattr(settings, "DISCORD_CONTEXT_REPO_PATH", str(tmp_path / "ctx"))


def _make_command(stdout=None):
    out = stdout or StringIO()
    return ExporterCommand(stdout=out)


def _collector(cmd: ExporterCommand, **opts):
    defaults = {
        "dry_run": False,
        "task": "all",
        "full_sync": False,
        "months": 12,
        "active_days": 30,
        "days_back": 30,
    }
    defaults.update(opts)
    return cmd.get_collector(**defaults)


@pytest.mark.django_db
def test_exporter_missing_user_token_writes_error(settings, monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_USER_TOKEN", None)
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", "1")
    monkeypatch.setattr(settings, "DISCORD_CONTEXT_REPO_PATH", "/x")
    buf = StringIO()
    cmd = ExporterCommand(stdout=buf)
    collector = DiscordExporterCollector(
        stdout=buf,
        style=cmd.style,
        dry_run=False,
        task="all",
        full_sync=False,
        months=12,
        active_days=30,
        days_back=30,
    )
    collector.run()
    assert "DISCORD_USER_TOKEN" in buf.getvalue()


@pytest.mark.django_db
def test_exporter_missing_server_id(settings, discord_exporter_settings, monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", None)
    buf = StringIO()
    cmd = ExporterCommand(stdout=buf)
    collector = DiscordExporterCollector(
        stdout=buf,
        style=cmd.style,
        dry_run=False,
        task="all",
        full_sync=False,
        months=12,
        active_days=30,
        days_back=30,
    )
    collector.run()
    assert "DISCORD_SERVER_ID" in buf.getvalue()


@pytest.mark.django_db
def test_exporter_missing_context_repo(
    settings, discord_exporter_settings, monkeypatch
):
    monkeypatch.setattr(settings, "DISCORD_CONTEXT_REPO_PATH", None)
    buf = StringIO()
    cmd = ExporterCommand(stdout=buf)
    collector = DiscordExporterCollector(
        stdout=buf,
        style=cmd.style,
        dry_run=False,
        task="all",
        full_sync=False,
        months=12,
        active_days=30,
        days_back=30,
    )
    collector.run()
    assert "DISCORD_CONTEXT_REPO_PATH" in buf.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_guild_to_json",
    return_value=[],
)
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_sync_first_sync_no_server(
    mock_raw, mock_export, discord_exporter_settings, tmp_path
):
    mock_raw.return_value = tmp_path
    cmd = _make_command()
    collector = _collector(cmd, task="sync")
    collector.run()
    mock_export.assert_called_once()
    assert (
        "First sync" in cmd.stdout.getvalue() or "Exported 0" in cmd.stdout.getvalue()
    )


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_guild_to_json",
    return_value=[],
)
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_sync_full_sync_with_days_back(
    mock_raw, mock_export, discord_exporter_settings, tmp_path
):
    mock_raw.return_value = tmp_path
    cmd = _make_command()
    collector = _collector(cmd, task="sync", full_sync=True, days_back=7)
    collector.run()
    assert "Full sync" in cmd.stdout.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_guild_to_json",
    return_value=[],
)
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_sync_incremental_with_channel_last_synced(
    mock_raw, mock_export, discord_exporter_settings, tmp_path
):
    mock_raw.return_value = tmp_path
    server = DiscordServer.objects.create(server_id=4242, server_name="Srv")
    ts = django_timezone.now()
    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=1,
        channel_name="general",
        channel_type="text",
        last_synced_at=ts,
    )
    cmd = _make_command()
    collector = _collector(cmd, task="sync", days_back=0)
    collector.run()
    assert ch.channel_name
    assert "Incremental sync" in cmd.stdout.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_guild_to_json",
    return_value=[],
)
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_sync_dry_run_lists_channels(
    mock_raw, mock_export, discord_exporter_settings, tmp_path
):
    mock_raw.return_value = tmp_path
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "guild": {"id": 1, "name": "G"},
                "channel": {"id": 2, "name": "c1"},
                "messages": [{"id": 1}],
            }
        ),
        encoding="utf-8",
    )
    mock_export.return_value = [p]
    cmd = _make_command()
    collector = _collector(cmd, task="sync", dry_run=True)
    collector.run()
    out = cmd.stdout.getvalue()
    assert "DRY RUN" in out
    assert "#c1" in out or "c1" in out


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_import_only_no_json(mock_raw, discord_exporter_settings, tmp_path):
    mock_raw.return_value = tmp_path
    cmd = _make_command()
    collector = _collector(cmd, task="import-only")
    collector.run()
    assert "No JSON files" in cmd.stdout.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_import_only_dry_run_lists_files(mock_raw, discord_exporter_settings, tmp_path):
    mock_raw.return_value = tmp_path
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    cmd = _make_command()
    collector = _collector(cmd, task="import-only", dry_run=True)
    collector.run()
    assert "a.json" in cmd.stdout.getvalue()


@pytest.mark.django_db
@patch("asyncio.run")
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.parse_exported_json",
)
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_import_only_parses_and_persists(
    mock_raw, mock_parse, mock_asyncio_run, discord_exporter_settings, tmp_path
):
    mock_raw.return_value = tmp_path
    f = tmp_path / "z.json"
    f.write_text("{}", encoding="utf-8")
    mock_parse.return_value = {
        "guild": {"id": 4242, "name": "G"},
        "channel": {"id": 9, "name": "ch"},
        "messages": [],
    }
    cmd = _make_command()
    collector = _collector(cmd, task="import-only", dry_run=False)
    collector.run()
    mock_asyncio_run.assert_called()
    assert "Imported" in cmd.stdout.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_and_push",
    return_value=True,
)
def test_export_markdown_success(mock_push, discord_exporter_settings, tmp_path):
    _ = DiscordServer.objects.create(server_id=4242, server_name="Srv")
    cmd = _make_command()
    collector = _collector(cmd, task="export", dry_run=False)
    collector.run()
    mock_push.assert_called_once()
    ctx = Path(settings.DISCORD_CONTEXT_REPO_PATH)
    assert str(ctx) in cmd.stdout.getvalue()


@pytest.mark.django_db
def test_export_markdown_server_missing(discord_exporter_settings):
    cmd = _make_command()
    collector = _collector(cmd, task="export", dry_run=False)
    collector.run()
    assert "not found in database" in cmd.stdout.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_and_push",
    return_value=False,
)
def test_export_markdown_no_files(mock_push, discord_exporter_settings):
    DiscordServer.objects.create(server_id=4242, server_name="Srv")
    cmd = _make_command()
    collector = _collector(cmd, task="export", dry_run=False)
    collector.run()
    assert "No files exported" in cmd.stdout.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_guild_to_json",
    return_value=[],
)
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_run_raises_propagates_after_logging(
    mock_raw, mock_export, discord_exporter_settings, tmp_path
):
    mock_raw.return_value = tmp_path
    mock_export.side_effect = RuntimeError("boom")
    cmd = _make_command()
    collector = _collector(cmd, task="sync")
    with pytest.raises(RuntimeError, match="boom"):
        collector.run()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.export_guild_to_json",
    return_value=[],
)
@patch(
    "discord_activity_tracker.management.commands.run_discord_exporter.get_raw_dir",
)
def test_call_command_invokes_exporter(
    mock_raw, mock_export, discord_exporter_settings, tmp_path
):
    mock_raw.return_value = tmp_path
    call_command("run_discord_exporter", task="sync", verbosity=0)
    mock_export.assert_called()
