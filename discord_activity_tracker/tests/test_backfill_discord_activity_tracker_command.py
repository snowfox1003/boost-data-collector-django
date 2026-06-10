"""Tests for backfill_discord_activity_tracker management command."""

import json
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.core.management import call_command

from discord_activity_tracker.management.commands.backfill_discord_activity_tracker import (
    Command,
    DiscordBackfillCollector,
)


def _collector(**overrides):
    defaults = {
        "stdout": StringIO(),
        "style": MagicMock(),
        "dry_run": False,
        "skip_pinecone": False,
    }
    defaults.update(overrides)
    c = DiscordBackfillCollector(**defaults)
    c.style.SUCCESS = lambda x: x
    c.style.WARNING = lambda x: x
    c.style.ERROR = lambda x: x
    return c


def _minimal_export_payload():
    return {
        "guild": {"id": "900", "name": "G", "iconUrl": ""},
        "channel": {
            "id": "851121440425639956",
            "name": "discussion",
            "type": "GuildTextChat",
            "topic": "",
            "category": "",
        },
        "messages": [
            {
                "id": "1399663560723923005",
                "type": "Default",
                "isPinned": False,
                "timestamp": "2026-01-01T12:00:00Z",
                "content": "hello world example text long enough",
                "author": {"id": "1082347485026070548", "name": "user"},
                "attachments": [],
                "reactions": [],
            }
        ],
    }


def test_run_removes_json_after_successful_persist(monkeypatch, tmp_path, settings):
    """After DB persist succeeds, the source JSON file is deleted."""
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    drop = tmp_path / "discord_activity_tracker" / "Discussion - c-cpp-discussion"
    drop.mkdir(parents=True)
    j = drop / "batch.json"
    j.write_text(json.dumps(_minimal_export_payload()), encoding="utf-8")

    c = _collector(skip_pinecone=True)
    with patch.object(
        DiscordBackfillCollector,
        "_persist_channel",
        new_callable=AsyncMock,
        return_value=1,
    ):
        c.run()

    assert not j.exists()


def test_run_finds_json_in_nested_subfolders(monkeypatch, tmp_path, settings):
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    drop = tmp_path / "discord_activity_tracker" / "Discussion - c-cpp-discussion"
    nested = drop / "a" / "b" / "c"
    nested.mkdir(parents=True)
    j = nested / "deep.json"
    j.write_text(json.dumps(_minimal_export_payload()), encoding="utf-8")

    c = _collector(skip_pinecone=True)
    with patch.object(
        DiscordBackfillCollector,
        "_persist_channel",
        new_callable=AsyncMock,
        return_value=1,
    ):
        c.run()

    assert not j.exists()


def test_run_keeps_file_on_invalid_json(monkeypatch, tmp_path, settings):
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    drop = tmp_path / "discord_activity_tracker" / "Discussion - c-cpp-discussion"
    drop.mkdir(parents=True)
    bad = drop / "bad.json"
    bad.write_text("{", encoding="utf-8")

    c = _collector(skip_pinecone=True)
    c.run()

    assert bad.exists()
    result = c.last_result
    assert result is not None
    assert result.success is False
    assert result.counts["failed_files"] == 1
    assert len(result.errors) == 1
    assert "bad.json" in result.errors[0]


def test_run_result_success_when_all_files_import(monkeypatch, tmp_path, settings):
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    drop = tmp_path / "discord_activity_tracker" / "Discussion - c-cpp-discussion"
    drop.mkdir(parents=True)
    j = drop / "batch.json"
    j.write_text(json.dumps(_minimal_export_payload()), encoding="utf-8")

    c = _collector(skip_pinecone=True)
    with patch.object(
        DiscordBackfillCollector,
        "_persist_channel",
        new_callable=AsyncMock,
        return_value=1,
    ):
        c.run()

    result = c.last_result
    assert result is not None
    assert result.success is True
    assert result.counts["failed_files"] == 0
    assert result.errors == ()


def test_dry_run_lists_files_no_delete(monkeypatch, tmp_path, settings):
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    drop = tmp_path / "discord_activity_tracker" / "Discussion - c-cpp-discussion"
    drop.mkdir(parents=True)
    j = drop / "batch.json"
    j.write_text(json.dumps(_minimal_export_payload()), encoding="utf-8")

    out = StringIO()
    c = DiscordBackfillCollector(
        stdout=out,
        style=MagicMock(),
        dry_run=True,
        skip_pinecone=True,
    )
    c.style.WARNING = lambda x: x
    c.run()

    assert j.exists()
    assert "dry-run" in out.getvalue().lower() or "DRY RUN" in out.getvalue()


@pytest.mark.django_db
def test_sync_pinecone_skipped_when_skip_pinecone():
    c = _collector(skip_pinecone=True)
    c.sync_pinecone()


@pytest.mark.django_db
def test_sync_pinecone_skipped_when_dry_run():
    c = _collector(dry_run=True)
    c.sync_pinecone()


@pytest.mark.django_db
def test_get_collector_returns_backfill_collector():
    cmd = Command()
    cmd.stdout = StringIO()
    cmd.style = MagicMock()
    collector = cmd.get_collector(dry_run=True, skip_pinecone=True)
    assert isinstance(collector, DiscordBackfillCollector)
    assert collector.dry_run is True


@pytest.mark.django_db
def test_call_command_dry_run(monkeypatch, tmp_path, settings):
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    tmp_path.joinpath(
        "discord_activity_tracker", "Discussion - c-cpp-discussion"
    ).mkdir(parents=True)
    out = StringIO()
    call_command(
        "backfill_discord_activity_tracker",
        dry_run=True,
        stdout=out,
        verbosity=0,
    )
    assert "DRY RUN" in out.getvalue() or "dry-run" in out.getvalue().lower()
