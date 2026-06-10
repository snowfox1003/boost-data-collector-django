"""Extra coverage for backfill_discord_activity_tracker command."""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from discord_activity_tracker.management.commands.backfill_discord_activity_tracker import (
    Command,
    DiscordBackfillCollector,
    _json_display_path,
)


def test_json_display_path_outside_import_root_returns_basename():
    assert _json_display_path(Path("/a/b"), Path("/x/other.json")) == "other.json"


@pytest.mark.django_db
def test_backfill_collector_sync_pinecone_calls_runner():
    style = MagicMock()
    style.SUCCESS = lambda x: x
    c = DiscordBackfillCollector(
        stdout=StringIO(), style=style, dry_run=False, skip_pinecone=False
    )
    with patch(
        "discord_activity_tracker.management.commands.backfill_discord_activity_tracker.task_discord_pinecone_sync"
    ) as t:
        c.sync_pinecone()
    t.assert_called_once_with(dry_run=False)


@pytest.mark.django_db
def test_backfill_collector_sync_pinecone_skipped_when_dry_run():
    style = MagicMock()
    c = DiscordBackfillCollector(
        stdout=StringIO(), style=style, dry_run=True, skip_pinecone=False
    )
    with patch(
        "discord_activity_tracker.management.commands.backfill_discord_activity_tracker.task_discord_pinecone_sync"
    ) as t:
        c.sync_pinecone()
    t.assert_not_called()


def test_backfill_get_collector_skip_pinecone_none():
    cmd = Command()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    c = cmd.get_collector(dry_run=False, skip_pinecone=None)
    assert c.skip_pinecone is False


@pytest.mark.django_db
def test_backfill_run_handles_bad_json(tmp_path, settings):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    imp = tmp_path / "import_here"
    imp.mkdir()
    bad = imp / "bad.json"
    bad.write_text("{", encoding="utf-8")

    style = MagicMock()
    style.WARNING = lambda x: x
    style.SUCCESS = lambda x: x
    style.ERROR = lambda x: x
    out = StringIO()

    with patch(
        "discord_activity_tracker.management.commands.backfill_discord_activity_tracker.get_cpp_discussion_import_dir",
        return_value=imp,
    ):
        DiscordBackfillCollector(
            stdout=out, style=style, dry_run=False, skip_pinecone=True
        ).run()

    output = out.getvalue()
    assert "bad.json" in output
    assert "Failed bad.json:" in output
    assert "Import complete: 0 messages from 1 file(s)" in output
    assert "(1 failed)" in output


@pytest.mark.django_db
def test_backfill_persist_channel_writes(settings, tmp_path):
    settings.WORKSPACE_DIR = tmp_path / "ws"
    settings.WORKSPACE_DIR.mkdir(parents=True)
    gid, cid = 220011, 220022
    guild_info = {"id": gid, "name": "G", "iconUrl": ""}
    channel_info = {
        "id": cid,
        "name": "c",
        "type": "GuildTextChat",
        "topic": "",
        "category": "",
        "categoryId": None,
    }
    messages = [
        {
            "id": str(10**12 + 3),
            "type": "Default",
            "isPinned": False,
            "timestamp": "2026-01-15T12:00:00Z",
            "content": "hello world example text long enough for validation",
            "author": {"id": "1082347485026070548", "name": "u"},
            "attachments": [],
            "reactions": [],
        }
    ]
    style = MagicMock()
    style.SUCCESS = lambda x: x
    c = DiscordBackfillCollector(
        stdout=StringIO(), style=style, dry_run=False, skip_pinecone=True
    )
    n = asyncio.run(c._persist_channel(guild_info, channel_info, messages))
    assert n >= 1
