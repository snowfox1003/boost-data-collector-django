"""Tests for run_cppa_slack_tracker management command and CppaSlackTrackerCollector."""

from __future__ import annotations

import json
from datetime import timezone
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from cppa_slack_tracker.management.commands.run_cppa_slack_tracker import (
    CppaSlackTrackerCollector,
    Command,
    _parse_date,
)


def test_parse_date_empty_and_invalid():
    assert _parse_date(None) is None
    assert _parse_date("") is None
    assert _parse_date("   ") is None
    assert _parse_date("not-a-date") is None


def test_parse_date_yyyy_mm_dd():
    dt = _parse_date("2024-06-01")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2024 and dt.month == 6 and dt.day == 1


def test_parse_date_iso_with_z():
    dt = _parse_date("2024-06-01T12:30:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def test_parse_date_iso_naive_gets_utc():
    dt = _parse_date("2024-06-01 08:00:00")
    assert dt is not None
    assert dt.tzinfo == timezone.utc


@pytest.mark.django_db
def test_command_errors_when_no_team_id(settings):
    settings.SLACK_TEAM_ID = ""
    cmd = Command()
    with pytest.raises(CommandError, match="Team ID is required"):
        cmd.get_collector(**{})


@pytest.mark.django_db
def test_get_collector_uses_team_id_from_options(settings, sample_slack_team):
    settings.SLACK_TEAM_ID = ""
    cmd = Command()
    collector = cmd.get_collector(
        team_id=sample_slack_team.team_id,
        channel_id=None,
        start_date=None,
        end_date=None,
        messages_json=None,
        sync_users=False,
        sync_channels=False,
        sync_channel_users=False,
        sync_messages=False,
        dry_run=False,
        ignore_pinecone=False,
    )
    assert isinstance(collector, CppaSlackTrackerCollector)
    assert collector.team_id == sample_slack_team.team_id


@pytest.mark.django_db
def test_get_collector_falls_back_to_settings_slack_team_id(
    settings, sample_slack_team
):
    settings.SLACK_TEAM_ID = sample_slack_team.team_id
    cmd = Command()
    collector = cmd.get_collector(
        team_id=None,
        channel_id=None,
        start_date=None,
        end_date=None,
        messages_json=None,
        sync_users=False,
        sync_channels=False,
        sync_channel_users=False,
        sync_messages=False,
        dry_run=False,
        ignore_pinecone=False,
    )
    assert collector.team_id == sample_slack_team.team_id


@pytest.mark.django_db
def test_collector_dry_run_exits_before_sync_team(caplog):
    caplog.set_level("INFO")
    collector = CppaSlackTrackerCollector(
        team_id="TDRYRUN",
        options={"dry_run": True},
    )
    with patch(
        "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team"
    ) as mock_sync_team:
        collector.run()
    mock_sync_team.assert_not_called()
    assert "Dry run" in caplog.text or "dry" in caplog.text.lower()


@pytest.mark.django_db
def test_collector_dry_run_with_channel_and_sync_flags(caplog):
    caplog.set_level("INFO")
    collector = CppaSlackTrackerCollector(
        team_id="T1",
        options={
            "dry_run": True,
            "channel_id": " CCHAN ",
            "sync_users": True,
            "sync_channels": True,
            "sync_channel_users": True,
            "sync_messages": True,
            "start_date": "2024-01-01",
            "end_date": "2024-01-02",
            "messages_json": "/tmp/legacy.json",
        },
    )
    collector.run()
    assert "Would run: sync users" in caplog.text


@pytest.mark.django_db
def test_collector_dry_run_default_branch_logs(caplog):
    caplog.set_level("INFO")
    collector = CppaSlackTrackerCollector(
        team_id="T1",
        options={"dry_run": True, "channel_id": "CX"},
    )
    collector.run()
    assert "Would run: sync users, channels, and messages" in caplog.text


@pytest.mark.django_db
def test_collector_only_sync_users_branch(sample_slack_team, caplog):
    caplog.set_level("INFO")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={"sync_users": True},
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(3, 1),
        ) as mock_users,
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels"
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages"
        ),
    ):
        collector.run()
    mock_users.assert_called_once()


@pytest.mark.django_db
def test_collector_only_sync_channels_branch(sample_slack_team, caplog):
    caplog.set_level("INFO")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={"sync_channels": True},
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(2, 0),
        ) as mock_ch,
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users"
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages"
        ),
    ):
        collector.run()
    mock_ch.assert_called_once()


@pytest.mark.django_db
def test_sync_pinecone_no_team_returns_early():
    collector = CppaSlackTrackerCollector(team_id="TX", options={})
    collector._team = None
    collector.sync_pinecone()


@pytest.mark.django_db
def test_collector_run_default_syncs_users_channels_messages(
    sample_slack_team, sample_slack_channel, caplog
):
    caplog.set_level("INFO")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={},
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ) as mock_team,
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(1, 0),
        ) as mock_users,
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(1, 0),
        ) as mock_ch,
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(2, 0),
        ) as mock_msg,
    ):
        collector.run()

    mock_team.assert_called_once_with(sample_slack_team.team_id)
    mock_users.assert_called_once()
    mock_ch.assert_called_once()
    mock_msg.assert_called()


@pytest.mark.django_db
def test_collector_sync_channel_users_only(sample_slack_team, caplog):
    caplog.set_level("INFO")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={"sync_channel_users": True},
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channel_users",
            return_value=(1, 0),
        ) as mock_cu,
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users"
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels"
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages"
        ),
    ):
        collector.run()
    mock_cu.assert_called_once()


@pytest.mark.django_db
def test_sync_messages_no_channels_warning(sample_slack_team, caplog):
    caplog.set_level("WARNING")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={"sync_messages": True},
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[],
        ),
    ):
        collector.run()
    assert "No channels to sync" in caplog.text


@pytest.mark.django_db
def test_collector_dry_run_default_branch_logs_messages_json_path(tmp_path, caplog):
    """Default dry-run path logs legacy JSON path (lines 155–159)."""
    caplog.set_level("INFO")
    legacy = tmp_path / "legacy.json"
    legacy.write_text("[]", encoding="utf-8")
    collector = CppaSlackTrackerCollector(
        team_id="T1",
        options={
            "dry_run": True,
            "messages_json": str(legacy),
        },
    )
    collector.run()
    assert "Would load legacy messages" in caplog.text


@pytest.mark.django_db
def test_collector_dry_run_messages_json_with_sync_messages_logged(tmp_path, caplog):
    caplog.set_level("INFO")
    legacy = tmp_path / "legacy2.json"
    legacy.write_text("[]", encoding="utf-8")
    collector = CppaSlackTrackerCollector(
        team_id="T1",
        options={
            "dry_run": True,
            "sync_messages": True,
            "messages_json": str(legacy),
        },
    )
    collector.run()
    assert "Would load legacy messages" in caplog.text


@pytest.mark.django_db
def test_load_messages_single_dict_json_file(
    tmp_path, sample_slack_team, sample_slack_channel
):
    p = tmp_path / "one.json"
    p.write_text(
        json.dumps(
            {
                "channel": sample_slack_channel.channel_id,
                "text": "solo",
                "ts": "2.0",
            },
        ),
        encoding="utf-8",
    )
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(p),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.save_slack_message"
        ),
        patch("os.path.exists", return_value=True),
    ):
        collector.run()


@pytest.mark.django_db
def test_load_messages_json_oserror_on_open(
    tmp_path, sample_slack_team, sample_slack_channel
):
    p = tmp_path / "gone.json"
    p.write_text("[]", encoding="utf-8")
    real_open = open

    def open_side(file, *args, **kwargs):
        if str(file) == str(p):
            raise OSError("denied")
        return real_open(file, *args, **kwargs)

    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(p),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch("builtins.open", side_effect=open_side),
        patch("os.path.isfile", return_value=True),
        patch("os.path.exists", return_value=True),
    ):
        collector.run()


@pytest.mark.django_db
def test_load_messages_skips_non_dict_and_unknown_channel(
    tmp_path, sample_slack_team, sample_slack_channel, caplog
):
    caplog.set_level("WARNING")
    p = tmp_path / "mix.json"
    p.write_text(
        json.dumps(
            [
                "not-a-dict",
                {
                    "channel": "C_UNKNOWN",
                    "ts": "1.0",
                },
                {
                    "channel": sample_slack_channel.channel_id,
                    "ts": "3.0",
                    "text": "ok",
                },
            ],
        ),
        encoding="utf-8",
    )
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(p),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.save_slack_message"
        ) as mock_save,
        patch("os.path.exists", return_value=True),
    ):
        collector.run()
    mock_save.assert_called_once()


@pytest.mark.django_db
def test_load_messages_save_raises_logs_exception(
    tmp_path, sample_slack_team, sample_slack_channel, caplog
):
    caplog.set_level("ERROR")
    p = tmp_path / "one.json"
    p.write_text(
        json.dumps(
            [{"channel": sample_slack_channel.channel_id, "ts": "9.0"}],
        ),
        encoding="utf-8",
    )
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(p),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.save_slack_message",
            side_effect=RuntimeError("db error"),
        ),
        patch("os.path.exists", return_value=True),
    ):
        collector.run()
    assert "Failed to save message" in caplog.text or "db error" in caplog.text


@pytest.mark.django_db
def test_sync_to_pinecone_logs_errors_list(caplog, sample_slack_team, settings):
    settings.PINECONE_SLACK_NAMESPACE_PREFIX = "ns"
    settings.PINECONE_SLACK_APP_TYPE_PREFIX = "app"
    caplog.set_level("WARNING")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={},
    )
    fake_result = {
        "upserted": 0,
        "total": 1,
        "failed_count": 1,
        "errors": ["e1", "e2", "e3", "e4"],
    }
    fake_services = MagicMock(sync_to_pinecone=MagicMock(return_value=fake_result))
    with (
        patch.dict("sys.modules", {"cppa_pinecone_sync.sync_api": fake_services}),
        patch("cppa_slack_tracker.preprocessor.preprocess_slack_for_pinecone"),
    ):
        collector._sync_to_pinecone(sample_slack_team)
    assert "Pinecone sync had" in caplog.text or "errors" in caplog.text.lower()


@pytest.mark.django_db
def test_sync_to_pinecone_generic_exception_logged(caplog, sample_slack_team, settings):
    settings.PINECONE_SLACK_NAMESPACE_PREFIX = "ns"
    settings.PINECONE_SLACK_APP_TYPE_PREFIX = "app"
    caplog.set_level("ERROR")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={},
    )
    fake_services = MagicMock(
        sync_to_pinecone=MagicMock(side_effect=RuntimeError("unexpected pinecone"))
    )
    with (
        patch.dict("sys.modules", {"cppa_pinecone_sync.sync_api": fake_services}),
        patch("cppa_slack_tracker.preprocessor.preprocess_slack_for_pinecone"),
    ):
        collector._sync_to_pinecone(sample_slack_team)
    assert "Error during Pinecone sync" in caplog.text


@pytest.mark.django_db
def test_load_messages_from_json_file(
    tmp_path, sample_slack_team, sample_slack_channel
):
    payload = [{"channel": sample_slack_channel.channel_id, "text": "hi", "ts": "1.0"}]
    p = tmp_path / "msgs.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(p),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.save_slack_message"
        ) as mock_save,
        patch("os.path.exists", return_value=True),
    ):
        collector.run()
    mock_save.assert_called()


@pytest.mark.django_db
def test_load_messages_invalid_json_logs(
    tmp_path, sample_slack_team, sample_slack_channel
):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(p),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch("os.path.exists", return_value=True),
    ):
        collector.run()


@pytest.mark.django_db
def test_load_messages_dir_with_invalid_json_file(
    tmp_path, sample_slack_team, sample_slack_channel, caplog
):
    d = tmp_path / "dir2"
    d.mkdir()
    (d / "bad.json").write_text("{", encoding="utf-8")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(d),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch("os.path.exists", return_value=True),
    ):
        collector.run()


@pytest.mark.django_db
def test_load_messages_from_directory(
    tmp_path, sample_slack_team, sample_slack_channel
):
    d = tmp_path / "dir"
    d.mkdir()
    (d / "a.json").write_text(
        json.dumps(
            [{"channel": sample_slack_channel.channel_id, "ts": "1.0"}],
        ),
        encoding="utf-8",
    )
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={
            "sync_messages": True,
            "messages_json": str(d),
        },
    )
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[sample_slack_channel],
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_messages",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.save_slack_message"
        ),
        patch("os.path.exists", return_value=True),
    ):
        collector.run()


@pytest.mark.django_db
def test_sync_pinecone_skipped_when_ignore_pinecone(sample_slack_team):
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={"ignore_pinecone": True, "dry_run": False},
    )
    collector._team = sample_slack_team
    collector.sync_pinecone()
    # no exception; early return


@pytest.mark.django_db
def test_sync_pinecone_skipped_when_dry_run(sample_slack_team):
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={"dry_run": True},
    )
    collector._team = sample_slack_team
    collector.sync_pinecone()


@pytest.mark.django_db
def test_sync_to_pinecone_import_error_direct(caplog, sample_slack_team):
    caplog.set_level("WARNING")
    import builtins

    real_import = builtins.__import__

    def boom_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cppa_pinecone_sync.sync_api":
            raise ImportError("missing pinecone")
        return real_import(name, globals, locals, fromlist, level)

    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={},
    )
    with patch.object(builtins, "__import__", boom_import):
        collector._sync_to_pinecone(sample_slack_team)
    assert "Pinecone sync skipped" in caplog.text


@pytest.mark.django_db
def test_sync_to_pinecone_success(sample_slack_team, settings):
    settings.PINECONE_SLACK_NAMESPACE_PREFIX = "ns"
    settings.PINECONE_SLACK_APP_TYPE_PREFIX = "app"
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={},
    )
    fake_result = {"upserted": 1, "total": 1, "failed_count": 0, "errors": []}
    fake_services = MagicMock(sync_to_pinecone=MagicMock(return_value=fake_result))
    with (
        patch.dict("sys.modules", {"cppa_pinecone_sync.sync_api": fake_services}),
        patch(
            "cppa_slack_tracker.preprocessor.preprocess_slack_for_pinecone",
            create=True,
        ),
    ):
        collector._sync_to_pinecone(sample_slack_team)


@pytest.mark.django_db
def test_sync_to_pinecone_value_error_warning(caplog, sample_slack_team, settings):
    settings.PINECONE_SLACK_NAMESPACE_PREFIX = "ns"
    settings.PINECONE_SLACK_APP_TYPE_PREFIX = "app"
    caplog.set_level("WARNING")
    collector = CppaSlackTrackerCollector(
        team_id=sample_slack_team.team_id,
        options={},
    )
    fake_services = MagicMock(
        sync_to_pinecone=MagicMock(side_effect=ValueError("bad config"))
    )
    with (
        patch.dict("sys.modules", {"cppa_pinecone_sync.sync_api": fake_services}),
        patch("cppa_slack_tracker.preprocessor.preprocess_slack_for_pinecone"),
    ):
        collector._sync_to_pinecone(sample_slack_team)
    assert "Pinecone sync skipped" in caplog.text


@pytest.mark.django_db
def test_call_command_dry_run_integration(settings, caplog):
    settings.SLACK_TEAM_ID = "TINTEG"
    caplog.set_level("INFO")
    out = StringIO()
    call_command(
        "run_cppa_slack_tracker",
        dry_run=True,
        stdout=out,
        stderr=StringIO(),
    )
    assert "Dry run" in caplog.text or out.getvalue() != ""


@pytest.mark.django_db
def test_call_command_with_explicit_team_id(settings, sample_slack_team, caplog):
    caplog.set_level("INFO")
    with (
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_team",
            return_value=sample_slack_team,
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_users",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.sync_channels",
            return_value=(0, 0),
        ),
        patch(
            "cppa_slack_tracker.management.commands.run_cppa_slack_tracker.get_channels_to_sync",
            return_value=[],
        ),
    ):
        call_command(
            "run_cppa_slack_tracker",
            team_id=sample_slack_team.team_id,
            stdout=StringIO(),
            stderr=StringIO(),
        )
