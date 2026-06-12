"""Extra branch coverage for sync/chat_exporter.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from discord_activity_tracker.sync.chat_exporter import (
    DiscordChatExporterError,
    _file_command_brief_description,
    _run_channels_listing,
    export_guild_to_json,
    parse_channels_command_stdout,
)


def test_file_command_brief_description_no_file_binary(tmp_path):
    with patch(
        "discord_activity_tracker.sync.chat_exporter.shutil.which", return_value=None
    ):
        assert _file_command_brief_description(tmp_path / "x") is None


def test_file_command_brief_description_subprocess_error(tmp_path):
    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter.shutil.which",
            return_value="/bin/file",
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.run",
            side_effect=OSError("nope"),
        ),
    ):
        assert _file_command_brief_description(tmp_path / "x") is None


def test_file_command_brief_description_nonzero_return(tmp_path):
    proc = MagicMock(returncode=1, stdout="", stderr="")
    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter.shutil.which",
            return_value="/bin/file",
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.run",
            return_value=proc,
        ),
    ):
        assert _file_command_brief_description(tmp_path / "x") is None


def test_run_channels_listing_failure_raises(tmp_path, monkeypatch):
    cli = tmp_path / "cli"
    cli.touch()
    monkeypatch.setattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET_DLL", None)
    proc = MagicMock(returncode=1, stdout="", stderr="err")
    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.run",
            return_value=proc,
        ),
    ):
        with pytest.raises(DiscordChatExporterError, match="channels"):
            _run_channels_listing(cli, "tok", 1, "None")


def test_run_channels_listing_success(monkeypatch, tmp_path):
    cli = tmp_path / "cli"
    cli.touch()
    monkeypatch.setattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET_DLL", None)
    proc = MagicMock(returncode=0, stdout="12345 | #general\n", stderr="")
    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.run",
            return_value=proc,
        ),
    ):
        ids = _run_channels_listing(cli, "tok", 1, "None")
    assert ids == [12345]


def test_export_guild_dotnet_dll_missing_raises(tmp_path, monkeypatch):
    out = tmp_path / "out"
    missing_dll = tmp_path / "nope.dll"
    monkeypatch.setattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET_DLL", str(missing_dll))
    with pytest.raises(DiscordChatExporterError, match="missing"):
        export_guild_to_json("t", 1, out)


def test_export_guild_dotnet_no_dotnet_binary_raises(tmp_path, monkeypatch):
    dll = tmp_path / "app.dll"
    dll.write_bytes(b"x")
    monkeypatch.setattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET_DLL", str(dll))
    monkeypatch.setattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET", "")
    with patch(
        "discord_activity_tracker.sync.chat_exporter.shutil.which", return_value=None
    ):
        with pytest.raises(DiscordChatExporterError, match="dotnet"):
            export_guild_to_json("t", 1, tmp_path / "o")


def test_export_guild_os_error_errno_8_wraps(tmp_path, monkeypatch):
    cli = tmp_path / "cli"
    cli.touch()
    monkeypatch.setattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET_DLL", None)
    err = OSError("exec format error")
    err.errno = 8
    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.validate_discord_chat_exporter_cli_architecture",
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter._export_guild_by_channel_day",
            side_effect=err,
        ),
    ):
        if sys.platform == "win32":
            pytest.skip("errno 8 branch is POSIX-only")
        with pytest.raises(DiscordChatExporterError, match="wrong executable format"):
            export_guild_to_json("t", 1, tmp_path / "o2", after_date=None)


def test_parse_channels_skips_thread_banner_lines():
    text = "* thread\n123 | #x\n"
    assert parse_channels_command_stdout(text) == [123]
