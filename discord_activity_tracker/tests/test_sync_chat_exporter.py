"""Tests for discord_activity_tracker.sync.chat_exporter."""

import json
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from discord_activity_tracker.sync.chat_exporter import (
    DiscordChatExporterError,
    _get_cli_path,
    convert_exporter_message_to_dict,
    export_and_parse_guild,
    export_guild_to_json,
    parse_exported_json,
)


def test_get_cli_path_joins_tools_exe(tmp_path):
    with patch(
        "discord_activity_tracker.sync.chat_exporter.get_workspace_root",
        return_value=tmp_path,
    ):
        assert _get_cli_path() == tmp_path / "tools" / "DiscordChatExporter.Cli.exe"


def test_export_guild_cli_missing_raises(tmp_path):
    with patch(
        "discord_activity_tracker.sync.chat_exporter._get_cli_path",
        return_value=tmp_path / "missing.exe",
    ):
        with pytest.raises(DiscordChatExporterError, match="CLI not found"):
            export_guild_to_json("tok", 1, tmp_path / "out")


def test_export_guild_success(tmp_path):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"

    proc = MagicMock()
    proc.stdout = StringIO("line1\n\n")
    proc.stderr.read.return_value = ""

    def wait():
        proc.returncode = 0
        out.mkdir(parents=True, exist_ok=True)
        (out / "guild.json").write_text("{}", encoding="utf-8")

    proc.wait = wait

    with patch(
        "discord_activity_tracker.sync.chat_exporter._get_cli_path", return_value=cli
    ), patch(
        "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
        return_value=proc,
    ):
        paths = export_guild_to_json("user-token", 42, out, include_threads="All")

    assert out / "guild.json" in paths


def test_export_guild_nonzero_exit_raises(tmp_path):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"

    proc = MagicMock()
    proc.stdout = StringIO("")
    proc.stderr.read.return_value = "boom"

    def wait():
        proc.returncode = 1

    proc.wait = wait

    with patch(
        "discord_activity_tracker.sync.chat_exporter._get_cli_path", return_value=cli
    ), patch(
        "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
        return_value=proc,
    ):
        with pytest.raises(DiscordChatExporterError, match="exit code"):
            export_guild_to_json("tok", 1, out)


def test_export_guild_unexpected_wraps(tmp_path):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")

    with patch(
        "discord_activity_tracker.sync.chat_exporter._get_cli_path", return_value=cli
    ), patch(
        "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
        side_effect=OSError("bad"),
    ):
        with pytest.raises(DiscordChatExporterError, match="Unexpected"):
            export_guild_to_json("tok", 1, tmp_path / "o")


def test_export_guild_adds_after_before_flags(tmp_path):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"
    captured = {}

    proc = MagicMock()
    proc.stdout = StringIO("")
    proc.stderr.read.return_value = ""

    def wait():
        proc.returncode = 0

    proc.wait = wait

    def popen(cmd, **_kwargs):
        captured["cmd"] = cmd
        return proc

    with patch(
        "discord_activity_tracker.sync.chat_exporter._get_cli_path", return_value=cli
    ), patch(
        "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
        side_effect=popen,
    ):
        export_guild_to_json(
            "tok",
            7,
            out,
            after_date=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            before_date=datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
        )

    cmd = captured["cmd"]
    assert "--after" in cmd and "--before" in cmd


def test_parse_exported_json_roundtrip(tmp_path):
    p = tmp_path / "x.json"
    data = {"guild": {"id": "1"}, "channel": {}, "messages": []}
    p.write_text(json.dumps(data), encoding="utf-8")
    assert parse_exported_json(p) == data


def test_parse_exported_json_invalid(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        parse_exported_json(p)


def test_parse_exported_json_io_error(tmp_path):
    p = tmp_path / "x.json"
    p.touch()
    with patch(
        "discord_activity_tracker.sync.chat_exporter.open",
        side_effect=OSError("read failed"),
    ):
        with pytest.raises(OSError, match="read failed"):
            parse_exported_json(p)


def test_convert_exporter_message_reference():
    raw = {
        "id": "10",
        "timestamp": "2026-01-01T00:00:00",
        "content": "c",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [],
        "reference": {"messageId": "9"},
    }
    out = convert_exporter_message_to_dict(raw)
    assert out["reference"]["message_id"] == "9"


def test_export_and_parse_skips_bad_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")

    with patch(
        "discord_activity_tracker.sync.chat_exporter.export_guild_to_json",
        return_value=[bad],
    ):
        assert export_and_parse_guild("t", 1, tmp_path / "o") == []


def test_export_and_parse_returns_channels(tmp_path):
    ok = tmp_path / "ok.json"
    ok.write_text(
        json.dumps(
            {"guild": {"id": "g"}, "channel": {"id": "c"}, "messages": [{"id": "1"}]}
        ),
        encoding="utf-8",
    )

    with patch(
        "discord_activity_tracker.sync.chat_exporter.export_guild_to_json",
        return_value=[ok],
    ):
        rows = export_and_parse_guild("t", 1, tmp_path / "o")

    assert len(rows) == 1
    assert rows[0]["guild"] == {"id": "g"}
    assert rows[0]["file_path"] == ok
