"""Coverage for task_discord_sync (fetch → persist → raw archive)."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discord_activity_tracker.management.commands.run_discord_activity_tracker import (
    DiscordActivityCollector,
    task_discord_sync,
)
from discord_activity_tracker.sync.chat_exporter import ChannelDayExport


def _phony_token() -> str:
    return secrets.token_hex(16)


def _channel_day_export(
    path,
    *,
    day_str: str = "2026-01-15",
    channel_id: int = 0,
) -> ChannelDayExport:
    return ChannelDayExport(path=path, day_str=day_str, channel_id=channel_id)


def _minimal_envelope(guild_id: int, channel_id: int):
    msg = {
        "id": str(10**12 + guild_id + channel_id),
        "type": "Default",
        "isPinned": False,
        "timestamp": "2026-01-15T12:00:00Z",
        "content": "hello world example text long enough for validation",
        "author": {"id": "1082347485026070548", "name": "user"},
        "attachments": [],
        "reactions": [],
    }
    return {
        "guild": {"id": str(guild_id), "name": "G"},
        "channel": {"id": str(channel_id), "name": "c", "type": "GuildTextChat"},
        "messages": [msg],
    }


@pytest.mark.django_db
def test_task_discord_sync_skip_returns_early(settings):
    tok = _phony_token()
    settings.DISCORD_USER_TOKEN = tok
    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})
    task_discord_sync(
        dry_run=False,
        skip_discord_sync=True,
        user_token=tok,
        guild_id=1,
        channel_ids=[],
        after_date=None,
        before_date=None,
        per_channel_incremental=False,
        collector=collector,
    )


@pytest.mark.django_db
def test_task_discord_sync_dry_run_returns_early(settings):
    tok = _phony_token()
    settings.DISCORD_USER_TOKEN = tok
    cmd = MagicMock()
    cmd.stdout = StringIO()
    collector = DiscordActivityCollector(cmd=cmd, options={})
    task_discord_sync(
        dry_run=True,
        skip_discord_sync=False,
        user_token=tok,
        guild_id=1,
        channel_ids=[],
        after_date=None,
        before_date=None,
        per_channel_incremental=False,
        collector=collector,
    )


@pytest.mark.django_db
def test_task_discord_sync_happy_path_rename_raw(settings, tmp_path, monkeypatch):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    tok = _phony_token()
    settings.DISCORD_USER_TOKEN = tok

    gid, cid = 880011, 880022
    staging = tmp_path / "staging"
    staging.mkdir()
    raw_ch = tmp_path / "raw" / str(gid) / str(cid)
    raw_ch.mkdir(parents=True)

    jpath = staging / "c.json"
    jpath.write_text(json.dumps(_minimal_envelope(gid, cid)), encoding="utf-8")

    def fake_export(**_kwargs):
        return [_channel_day_export(jpath, day_str="2026-01-15", channel_id=cid)]

    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})
    collector._persist_channel = AsyncMock(return_value=1)

    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_guild_to_json",
            side_effect=fake_export,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_exporter_staging_dir",
            return_value=staging,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.clear_exporter_staging_dir",
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_channel_raw_dir",
            return_value=raw_ch,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_raw_dir",
            return_value=tmp_path / "raw",
        ),
    ):
        task_discord_sync(
            dry_run=False,
            skip_discord_sync=False,
            user_token=tok,
            guild_id=gid,
            channel_ids=[],
            after_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            before_date=None,
            per_channel_incremental=False,
            collector=collector,
        )

    dest = raw_ch / "2026-01-15.json"
    assert dest.is_file()
    assert not jpath.exists()


@pytest.mark.django_db
def test_task_discord_sync_skips_channel_not_in_allowlist(settings, tmp_path):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    tok = _phony_token()

    gid, cid = 770011, 770022
    staging = tmp_path / "st2"
    staging.mkdir()
    jpath = staging / "x.json"
    jpath.write_text(json.dumps(_minimal_envelope(gid, cid)), encoding="utf-8")

    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})
    collector._persist_channel = AsyncMock(return_value=0)

    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_guild_to_json",
            return_value=[
                _channel_day_export(jpath, day_str="2026-01-15", channel_id=cid)
            ],
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_exporter_staging_dir",
            return_value=staging,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.clear_exporter_staging_dir",
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_channel_raw_dir",
            return_value=tmp_path / "raw" / str(gid) / str(cid),
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_raw_dir",
            return_value=tmp_path / "raw",
        ),
    ):
        task_discord_sync(
            dry_run=False,
            skip_discord_sync=False,
            user_token=tok,
            guild_id=gid,
            channel_ids=[999999],
            after_date=None,
            before_date=None,
            per_channel_incremental=False,
            collector=collector,
        )

    assert not jpath.exists()


@pytest.mark.django_db
def test_task_discord_sync_staging_validation_error_keeps_file(
    settings, tmp_path, monkeypatch
):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    tok = _phony_token()
    gid, cid = 660011, 660022
    staging = tmp_path / "st3"
    staging.mkdir()
    jpath = staging / "bad.json"
    jpath.write_text(
        json.dumps({"guild": {}, "channel": {}, "messages": "bad"}), encoding="utf-8"
    )

    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})

    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_guild_to_json",
            return_value=[
                _channel_day_export(jpath, day_str="2026-01-15", channel_id=cid)
            ],
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_exporter_staging_dir",
            return_value=staging,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.clear_exporter_staging_dir",
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_channel_raw_dir",
            return_value=tmp_path / "raw" / str(gid) / str(cid),
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_raw_dir",
            return_value=tmp_path / "raw",
        ),
    ):
        task_discord_sync(
            dry_run=False,
            skip_discord_sync=False,
            user_token=tok,
            guild_id=gid,
            channel_ids=[],
            after_date=None,
            before_date=None,
            per_channel_incremental=False,
            collector=collector,
        )
    assert jpath.is_file()


@pytest.mark.django_db
def test_task_discord_sync_value_error_unlinks(settings, tmp_path):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    tok = _phony_token()
    gid, cid = 550011, 550022
    staging = tmp_path / "st4"
    staging.mkdir()
    jpath = staging / "v.json"
    jpath.write_text("{", encoding="utf-8")

    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})

    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_guild_to_json",
            return_value=[
                _channel_day_export(jpath, day_str="2026-01-15", channel_id=cid)
            ],
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_exporter_staging_dir",
            return_value=staging,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.clear_exporter_staging_dir",
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_channel_raw_dir",
            return_value=tmp_path / "raw" / str(gid) / str(cid),
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_raw_dir",
            return_value=tmp_path / "raw",
        ),
    ):
        task_discord_sync(
            dry_run=False,
            skip_discord_sync=False,
            user_token=tok,
            guild_id=gid,
            channel_ids=[],
            after_date=None,
            before_date=None,
            per_channel_incremental=False,
            collector=collector,
        )
    assert not jpath.exists()


@pytest.mark.django_db
def test_task_discord_sync_exporter_error_becomes_command_error(settings, tmp_path):
    from django.core.management.base import CommandError

    from discord_activity_tracker.sync.chat_exporter import DiscordChatExporterError

    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    tok = _phony_token()
    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})
    with patch(
        "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_guild_to_json",
        side_effect=DiscordChatExporterError("boom"),
    ):
        with pytest.raises(CommandError, match="DiscordChatExporter"):
            task_discord_sync(
                dry_run=False,
                skip_discord_sync=False,
                user_token=tok,
                guild_id=1,
                channel_ids=[],
                after_date=None,
                before_date=None,
                per_channel_incremental=False,
                collector=collector,
            )


@pytest.mark.django_db
def test_task_discord_sync_persist_raises_unlinks(settings, tmp_path):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    tok = _phony_token()
    gid, cid = 440011, 440022
    staging = tmp_path / "st5"
    staging.mkdir()
    jpath = staging / "ok.json"
    jpath.write_text(json.dumps(_minimal_envelope(gid, cid)), encoding="utf-8")

    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})
    collector._persist_channel = AsyncMock(side_effect=RuntimeError("db"))

    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_guild_to_json",
            return_value=[
                _channel_day_export(jpath, day_str="2026-01-15", channel_id=cid)
            ],
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_exporter_staging_dir",
            return_value=staging,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.clear_exporter_staging_dir",
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_channel_raw_dir",
            return_value=tmp_path / "raw" / str(gid) / str(cid),
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_raw_dir",
            return_value=tmp_path / "raw",
        ),
    ):
        task_discord_sync(
            dry_run=False,
            skip_discord_sync=False,
            user_token=tok,
            guild_id=gid,
            channel_ids=[],
            after_date=None,
            before_date=None,
            per_channel_incremental=False,
            collector=collector,
        )
    assert not jpath.exists()


@pytest.mark.django_db
def test_task_discord_sync_stdout_includes_before_date(settings, tmp_path):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    tok = _phony_token()
    gid, cid = 410011, 410022
    staging = tmp_path / "st6"
    staging.mkdir()
    jpath = staging / "bd.json"
    jpath.write_text(json.dumps(_minimal_envelope(gid, cid)), encoding="utf-8")

    cmd = MagicMock()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = lambda x: x
    collector = DiscordActivityCollector(cmd=cmd, options={})
    collector._persist_channel = AsyncMock(return_value=0)
    before = datetime(2026, 12, 31, tzinfo=timezone.utc)
    with (
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.export_guild_to_json",
            return_value=[
                _channel_day_export(jpath, day_str="2026-01-15", channel_id=cid)
            ],
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_exporter_staging_dir",
            return_value=staging,
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.clear_exporter_staging_dir",
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_channel_raw_dir",
            return_value=tmp_path / "raw" / str(gid) / str(cid),
        ),
        patch(
            "discord_activity_tracker.management.commands.run_discord_activity_tracker.get_raw_dir",
            return_value=tmp_path / "raw",
        ),
    ):
        task_discord_sync(
            dry_run=False,
            skip_discord_sync=False,
            user_token=tok,
            guild_id=gid,
            channel_ids=[],
            after_date=None,
            before_date=before,
            per_channel_incremental=False,
            collector=collector,
        )
    out = cmd.stdout.getvalue()
    assert "Upper bound" in out
