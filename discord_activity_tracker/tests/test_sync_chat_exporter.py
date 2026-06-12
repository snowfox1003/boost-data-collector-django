"""Tests for discord_activity_tracker.sync.chat_exporter."""

import json
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from discord_activity_tracker.sync.chat_exporter import (
    ChannelDayExport,
    DiscordChatExporterError,
    _sorted_discord_export_json_paths,
    filter_discord_export_json_paths,
    _get_cli_path,
    convert_exporter_message_to_dict,
    export_and_parse_guild,
    export_guild_to_json,
    parse_channels_command_stdout,
    parse_exported_json,
    validate_discord_chat_exporter_cli_architecture,
)


def test_filter_discord_export_json_paths_drops_dot_underscore(tmp_path):
    real = tmp_path / "Together.json"
    sidecar = tmp_path / "._Together.json"
    real.touch()
    sidecar.touch()
    assert filter_discord_export_json_paths([real, sidecar]) == [real]


def test_sorted_discord_export_json_paths_skips_appledouble_sidecars(tmp_path):
    d = tmp_path / "staging"
    d.mkdir()
    (d / "Together.json").write_text("{}", encoding="utf-8")
    (d / "._Together.json").write_bytes(b"\xb0not utf8")
    assert _sorted_discord_export_json_paths(d) == [d / "Together.json"]


def test_get_cli_path_defaults_to_workspace_script_on_windows(tmp_path, settings):
    settings.DISCORD_CHAT_EXPORTER_CLI = None
    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter.get_workspace_root",
            return_value=tmp_path,
        ),
        patch("sys.platform", "win32"),
    ):
        assert _get_cli_path() == tmp_path / "script" / "DiscordChatExporter.Cli.exe"


def test_get_cli_path_defaults_to_workspace_script_on_macos(tmp_path, settings):
    settings.DISCORD_CHAT_EXPORTER_CLI = None
    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter.get_workspace_root",
            return_value=tmp_path,
        ),
        patch("sys.platform", "darwin"),
    ):
        assert _get_cli_path() == tmp_path / "script" / "DiscordChatExporter.Cli"


def test_get_cli_path_respects_discord_chat_exporter_cli_env(settings, tmp_path):
    custom = tmp_path / "my-cli.exe"
    custom.write_text("fake", encoding="utf-8")
    settings.DISCORD_CHAT_EXPORTER_CLI = str(custom)
    assert _get_cli_path() == custom.resolve()


def test_cli_missing_error_includes_releases_url(tmp_path):
    with patch(
        "discord_activity_tracker.sync.chat_exporter._get_cli_path",
        return_value=tmp_path / "missing.exe",
    ):
        with pytest.raises(
            DiscordChatExporterError, match="Tyrrrz/DiscordChatExporter"
        ):
            export_guild_to_json("tok", 1, tmp_path / "out")


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
    channel_id = 100
    day_str = "2026-01-02"
    after = datetime(2026, 1, 2, tzinfo=timezone.utc)
    before = datetime(2026, 1, 3, tzinfo=timezone.utc)

    proc = MagicMock()
    proc.stdout = StringIO("line1\n\n")
    proc.stderr.read.return_value = ""

    def wait():
        proc.returncode = 0
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{channel_id}_{day_str}.json").write_text("{}", encoding="utf-8")

    proc.wait = wait

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            return_value=proc,
        ),
    ):
        exports = export_guild_to_json(
            "user-token",
            42,
            out,
            channel_ids=[channel_id],
            after_date=after,
            before_date=before,
            include_threads="All",
        )

    assert len(exports) == 1
    assert exports[0].path == out / f"{channel_id}_{day_str}.json"
    assert exports[0].day_str == day_str


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

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            return_value=proc,
        ),
    ):
        with pytest.raises(DiscordChatExporterError, match="exit code"):
            export_guild_to_json(
                "tok",
                1,
                out,
                channel_ids=[1],
                after_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
                before_date=datetime(2026, 1, 3, tzinfo=timezone.utc),
            )


def test_export_guild_auth_failure_retries_with_reextracted_token(tmp_path, settings):
    settings.ALLOW_INTERNAL_DISCORD_TOKENS = True
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"

    call_count = {"n": 0}

    def make_proc():
        proc = MagicMock()
        proc.stdout = StringIO("line1\n")
        if call_count["n"] == 0:
            proc.stderr.read.return_value = "HTTP 401 Unauthorized"
            proc.wait = lambda: setattr(proc, "returncode", 1) or None
        else:
            proc.stderr.read.return_value = ""

            def wait_ok():
                proc.returncode = 0
                out.mkdir(parents=True, exist_ok=True)
                (out / "100_2026-01-02.json").write_text("{}", encoding="utf-8")

            proc.wait = wait_ok
        call_count["n"] += 1
        return proc

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            side_effect=lambda *a, **k: make_proc(),
        ),
        patch(
            "discord_activity_tracker.utils.discord_internal_tokens_store.extract_and_save_discord_internal_tokens",
            return_value="fresh-tok",
        ),
    ):
        exports = export_guild_to_json(
            "old-tok",
            42,
            out,
            channel_ids=[100],
            after_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
            before_date=datetime(2026, 1, 3, tzinfo=timezone.utc),
        )

    assert call_count["n"] == 2
    assert exports[0].path == out / "100_2026-01-02.json"


def test_export_guild_unexpected_wraps(tmp_path):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            side_effect=OSError("bad"),
        ),
    ):
        with pytest.raises(DiscordChatExporterError, match="Unexpected"):
            export_guild_to_json(
                "tok",
                1,
                tmp_path / "o",
                channel_ids=[1],
                after_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
                before_date=datetime(2026, 1, 3, tzinfo=timezone.utc),
            )


def test_export_guild_output_path_is_explicit_json_file(tmp_path):
    """Per-day export passes an explicit ``-o`` JSON file path (no directory slash)."""
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"
    captured = {}

    proc = MagicMock()
    proc.stdout = StringIO("")
    proc.stderr.read.return_value = ""

    def wait():
        proc.returncode = 0
        out.mkdir(parents=True, exist_ok=True)
        (out / "1_2026-01-02.json").write_text("{}", encoding="utf-8")

    proc.wait = wait

    def popen(cmd, **_kwargs):
        captured["cmd"] = cmd
        return proc

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            side_effect=popen,
        ),
    ):
        export_guild_to_json(
            "tok",
            1,
            out,
            channel_ids=[1],
            after_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
            before_date=datetime(2026, 1, 3, tzinfo=timezone.utc),
        )

    output_index = captured["cmd"].index("--output") + 1
    output_value = captured["cmd"][output_index]
    assert output_value.endswith("1_2026-01-02.json")


def test_export_guild_per_channel_parallel_is_one(tmp_path, settings):
    settings.DISCORD_CHAT_EXPORTER_PARALLEL = 4
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"
    captured = {}

    proc = MagicMock()
    proc.stdout = StringIO("")
    proc.stderr.read.return_value = ""

    def wait():
        proc.returncode = 0
        out.mkdir(parents=True, exist_ok=True)
        (out / "1_2026-01-02.json").write_text("{}", encoding="utf-8")

    proc.wait = wait

    def popen(cmd, **_kwargs):
        captured["cmd"] = cmd
        return proc

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            side_effect=popen,
        ),
    ):
        export_guild_to_json(
            "tok",
            1,
            out,
            channel_ids=[1],
            after_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
            before_date=datetime(2026, 1, 3, tzinfo=timezone.utc),
        )

    par_idx = captured["cmd"].index("--parallel")
    assert captured["cmd"][par_idx + 1] == "1"


def test_parse_channels_command_stdout_skips_threads_and_banner():
    text = (
        "Some banner line\n"
        "851121440425639956 | #cpp-discussion\n"
        "  * 999888777666555444 | Thread / foo | Active\n"
        "123456789012345678 | voice-room\n"
    )
    assert parse_channels_command_stdout(text) == [
        851121440425639956,
        123456789012345678,
    ]


def test_parse_channels_command_stdout_empty():
    assert parse_channels_command_stdout("") == []


def test_validate_cli_rejects_intel_only_on_arm64_mac(tmp_path, monkeypatch):
    cli = tmp_path / "DiscordChatExporter.Cli"
    cli.write_bytes(b"\x00")
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "discord_activity_tracker.sync.chat_exporter._file_command_brief_description",
        lambda _p: "Mach-O 64-bit executable x86_64",
    )
    with pytest.raises(DiscordChatExporterError, match="Intel-only"):
        validate_discord_chat_exporter_cli_architecture(cli)


def test_validate_cli_accepts_arm64_on_arm64_mac(tmp_path, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO)
    cli = tmp_path / "DiscordChatExporter.Cli"
    cli.write_bytes(b"\x00")
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "discord_activity_tracker.sync.chat_exporter._file_command_brief_description",
        lambda _p: "Mach-O 64-bit executable arm64",
    )
    validate_discord_chat_exporter_cli_architecture(cli)
    assert any("arch check OK" in r.message for r in caplog.records)


def test_validate_cli_skips_windows(tmp_path, monkeypatch):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_bytes(b"\x00")
    monkeypatch.setattr("sys.platform", "win32")
    validate_discord_chat_exporter_cli_architecture(cli)  # no raise


def test_export_guild_sigkill_error_message_hints_parallel(tmp_path):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"

    proc = MagicMock()
    proc.stdout = StringIO("")
    proc.stderr.read.return_value = ""

    def wait():
        proc.returncode = -9

    proc.wait = wait

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            return_value=proc,
        ),
    ):
        with pytest.raises(DiscordChatExporterError, match="SIGKILL"):
            export_guild_to_json(
                "tok",
                1,
                out,
                channel_ids=[1],
                after_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
                before_date=datetime(2026, 1, 3, tzinfo=timezone.utc),
            )


def test_sequential_export_skips_channels_cli_when_channel_ids_set(tmp_path, settings):
    """Explicit allowlist avoids `channels` subprocess (SIGKILL/OOM on huge guilds)."""
    settings.DISCORD_CHAT_EXPORTER_SEQUENTIAL_EXPORT = True
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"
    run_calls: list[list[str]] = []
    day_str = "2026-01-01"
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    before = datetime(2026, 1, 2, tzinfo=timezone.utc)

    def capture_run(cmd, **_kwargs):
        run_calls.append(list(cmd))

        class R:
            returncode = 1

        return R()

    def make_popen(cmd, **_kwargs):
        assert cmd[1] == "export"
        ch = cmd[cmd.index("--channel") + 1]
        proc = MagicMock()
        proc.stdout = StringIO("")
        proc.stderr.read.return_value = ""

        def wait():
            proc.returncode = 0
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{ch}_{day_str}.json").write_text("{}", encoding="utf-8")

        proc.wait = wait
        return proc

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.validate_discord_chat_exporter_cli_architecture",
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.run",
            side_effect=capture_run,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            side_effect=make_popen,
        ),
    ):
        exports = export_guild_to_json(
            "tok",
            1,
            out,
            channel_ids=[222, 111, 222],
            after_date=after,
            before_date=before,
        )

    assert run_calls == []
    assert len(exports) == 2


def test_export_guild_adds_after_before_flags(tmp_path):
    cli = tmp_path / "DiscordChatExporter.Cli.exe"
    cli.write_text("fake", encoding="utf-8")
    out = tmp_path / "exp"
    captured_cmds: list[list[str]] = []

    proc = MagicMock()
    proc.stdout = StringIO("")
    proc.stderr.read.return_value = ""

    def wait():
        proc.returncode = 0
        out.mkdir(parents=True, exist_ok=True)
        (out / "7_2026-01-02.json").write_text("{}", encoding="utf-8")

    proc.wait = wait

    def popen(cmd, **_kwargs):
        captured_cmds.append(list(cmd))
        return proc

    with (
        patch(
            "discord_activity_tracker.sync.chat_exporter._get_cli_path",
            return_value=cli,
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.validate_discord_chat_exporter_cli_architecture",
        ),
        patch(
            "discord_activity_tracker.sync.chat_exporter.subprocess.Popen",
            side_effect=popen,
        ),
    ):
        export_guild_to_json(
            "tok",
            7,
            out,
            channel_ids=[7],
            after_date=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            before_date=datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
        )

    assert captured_cmds
    assert any("--after" in cmd and "--before" in cmd for cmd in captured_cmds)


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
    # reference messageId should be coerced to int
    assert out["reference"]["message_id"] == 9


# --- new: ID coercion, emoji flattening, avatarUrl, message_type, is_pinned ---


def test_convert_exporter_message_ids_are_int():
    """All snowflake IDs must be coerced from string to int."""
    raw = {
        "id": "1399663560723923005",
        "type": "Default",
        "isPinned": False,
        "timestamp": "2025-07-29T04:03:17.368-04:00",
        "content": "hello",
        "author": {"id": "1082347485026070548", "name": "raubtier"},
        "attachments": [],
        "reactions": [],
    }
    out = convert_exporter_message_to_dict(raw)
    assert out["id"] == 1399663560723923005
    assert isinstance(out["id"], int)
    assert out["author"]["id"] == 1082347485026070548
    assert isinstance(out["author"]["id"], int)


def test_convert_exporter_message_canonical_fields_with_server_channel():
    raw = {
        "id": "10",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "c",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [],
    }
    out = convert_exporter_message_to_dict(raw, server_id=99, channel_id=100)
    assert out["actor_id"] == "1"
    assert out["occurred_at"] == "2026-01-01T00:00:00Z"
    assert out["source_url"] == "https://discord.com/channels/99/100/10"


def test_convert_exporter_message_reaction_emoji_flattened():
    """Reaction emoji dict must be flattened to a plain string."""
    raw = {
        "id": "1",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [
            {"emoji": {"id": None, "name": "👍", "isAnimated": False}, "count": 3}
        ],
    }
    out = convert_exporter_message_to_dict(raw)
    assert out["reactions"][0]["emoji"] == "👍"
    assert out["reactions"][0]["count"] == 3


def test_convert_exporter_message_reaction_malformed_count_defaults():
    raw = {
        "id": "1",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [
            {"emoji": {"name": "x"}, "count": "not-a-number"},
            {"emoji": {"name": "y"}, "count": -2},
        ],
    }
    out = convert_exporter_message_to_dict(raw)
    assert len(out["reactions"]) == 2
    assert out["reactions"][0]["count"] == 0
    assert out["reactions"][1]["count"] == 0


def test_convert_exporter_message_reaction_null_emoji_is_dropped():
    raw = {
        "id": "1",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [{"emoji": None, "count": 1}],
    }
    out = convert_exporter_message_to_dict(raw)
    assert out["reactions"] == []


def test_convert_exporter_message_avatarUrl_mapped():
    """Author avatarUrl must be mapped to avatar_url."""
    raw = {
        "id": "2",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "hi",
        "author": {
            "id": "5",
            "name": "hero",
            "avatarUrl": "https://cdn.discordapp.com/avatars/avatar.png",
        },
        "attachments": [],
        "reactions": [],
    }
    out = convert_exporter_message_to_dict(raw)
    assert (
        out["author"]["avatar_url"] == "https://cdn.discordapp.com/avatars/avatar.png"
    )


def test_convert_exporter_message_type_and_is_pinned():
    raw = {
        "id": "3",
        "type": "Reply",
        "isPinned": True,
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "reply here",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [],
    }
    out = convert_exporter_message_to_dict(raw)
    assert out["message_type"] == "Reply"
    assert out["is_pinned"] is True


def test_convert_exporter_message_type_defaults_to_default():
    raw = {
        "id": "4",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "x",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [],
    }
    out = convert_exporter_message_to_dict(raw)
    assert out["message_type"] == "Default"
    assert out["is_pinned"] is False


def test_convert_exporter_reference_message_id_int():
    """reference.messageId snowflake string must be coerced to int."""
    raw = {
        "id": "10",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "reply",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [],
        "reference": {"messageId": "1399663560723923000"},
    }
    out = convert_exporter_message_to_dict(raw)
    assert out["reference"]["message_id"] == 1399663560723923000
    assert isinstance(out["reference"]["message_id"], int)


def test_export_and_parse_skips_bad_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")

    with patch(
        "discord_activity_tracker.sync.chat_exporter.export_guild_to_json",
        return_value=[ChannelDayExport(path=bad, day_str="2026-01-01", channel_id=1)],
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
        return_value=[ChannelDayExport(path=ok, day_str="2026-01-01", channel_id=1)],
    ):
        rows = export_and_parse_guild("t", 1, tmp_path / "o")

    assert len(rows) == 1
    assert rows[0]["guild"] == {"id": "g"}
    assert rows[0]["file_path"] == ok


def test_convert_exporter_message_with_embeds_key_ignored():
    raw = {
        "id": "1",
        "timestamp": "2026-01-01T00:00:00Z",
        "content": "body",
        "author": {"id": "1", "name": "a"},
        "attachments": [],
        "reactions": [],
        "embeds": [{"title": "E", "description": "d"}],
    }
    out = convert_exporter_message_to_dict(raw, server_id=1, channel_id=2)
    assert out["content"] == "body"
    assert "embeds" not in out
    from discord_activity_tracker.staging_schema import validate_normalized_message

    validate_normalized_message(out, source="embed-test")
