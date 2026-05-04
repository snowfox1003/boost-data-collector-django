"""Tests for run_discord_activity_tracker management command."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone as django_timezone

from discord_activity_tracker.models import DiscordChannel, DiscordServer


@pytest.fixture
def discord_activity_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DISCORD_TOKEN", "bot-token")
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 9999)
    monkeypatch.setattr(settings, "DISCORD_CONTEXT_REPO_PATH", str(tmp_path / "ctx"))


@pytest.mark.django_db
def test_missing_discord_token(monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_TOKEN", None)
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", 1)
    monkeypatch.setattr(settings, "DISCORD_CONTEXT_REPO_PATH", "/x")
    out = StringIO()
    call_command("run_discord_activity_tracker", stdout=out, verbosity=0)
    assert "DISCORD_TOKEN" in out.getvalue()


@pytest.mark.django_db
def test_missing_guild_id(discord_activity_settings, monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_SERVER_ID", None)
    out = StringIO()
    call_command("run_discord_activity_tracker", stdout=out, verbosity=0)
    assert "DISCORD_SERVER_ID" in out.getvalue()


@pytest.mark.django_db
def test_missing_context_repo(discord_activity_settings, monkeypatch):
    monkeypatch.setattr(settings, "DISCORD_CONTEXT_REPO_PATH", None)
    out = StringIO()
    call_command("run_discord_activity_tracker", stdout=out, verbosity=0)
    assert "DISCORD_CONTEXT_REPO_PATH" in out.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_activity_tracker.sync_all_channels"
)
def test_sync_task_calls_api(mock_sync, discord_activity_settings):
    DiscordServer.objects.create(server_id=9999, server_name="Test Guild")
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        task="sync",
        stdout=out,
        verbosity=0,
    )
    mock_sync.assert_called_once()
    assert "Synced" in out.getvalue()


@pytest.mark.django_db
def test_sync_dry_run_no_server(discord_activity_settings):
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        task="sync",
        dry_run=True,
        stdout=out,
        verbosity=0,
    )
    assert "first time" in out.getvalue()


@pytest.mark.django_db
def test_sync_dry_run_with_server_and_channels(discord_activity_settings):
    server = DiscordServer.objects.create(server_id=9999, server_name="G")
    DiscordChannel.objects.create(
        server=server,
        channel_id=1,
        channel_name="general",
        channel_type="text",
        last_activity_at=django_timezone.now(),
    )
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        task="sync",
        dry_run=True,
        stdout=out,
        verbosity=0,
    )
    assert "Would sync" in out.getvalue()
    assert "#general" in out.getvalue()


@pytest.mark.django_db
def test_export_task_server_missing(discord_activity_settings):
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        task="export",
        stdout=out,
        verbosity=0,
    )
    assert "not found" in out.getvalue().lower()


@pytest.mark.django_db
def test_export_dry_run_lists_channels(discord_activity_settings):
    server = DiscordServer.objects.create(server_id=9999, server_name="G")
    DiscordChannel.objects.create(
        server=server,
        channel_id=2,
        channel_name="news",
        channel_type="text",
        last_activity_at=django_timezone.now(),
    )
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        task="export",
        dry_run=True,
        stdout=out,
        verbosity=0,
    )
    assert "#news" in out.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_and_push",
    return_value=True,
)
def test_export_task_success(mock_push, discord_activity_settings):
    DiscordServer.objects.create(server_id=9999, server_name="G")
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        task="export",
        stdout=out,
        verbosity=0,
    )
    mock_push.assert_called_once()
    assert "Exported" in out.getvalue()


@pytest.mark.django_db
@patch(
    "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_and_push",
    return_value=False,
)
def test_export_task_failure(mock_push, discord_activity_settings):
    DiscordServer.objects.create(server_id=9999, server_name="G")
    out = StringIO()
    call_command(
        "run_discord_activity_tracker",
        task="export",
        stdout=out,
        verbosity=0,
    )
    assert "failed" in out.getvalue().lower()
