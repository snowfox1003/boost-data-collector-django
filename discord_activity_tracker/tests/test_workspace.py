"""Tests for discord_activity_tracker.workspace."""

from unittest.mock import patch

import pytest

from discord_activity_tracker.workspace import (
    get_channel_json_path,
    get_channel_raw_dir,
    get_messages_json_path,
    get_raw_dir,
    get_server_dir,
    get_workspace_root,
    iter_existing_message_jsons,
)


@pytest.fixture
def mock_discord_workspace(tmp_path):
    root = tmp_path / "discord_activity_tracker"
    root.mkdir(parents=True)
    return root


def test_get_workspace_root(mock_discord_workspace):
    with patch(
        "discord_activity_tracker.workspace.get_workspace_path",
        return_value=mock_discord_workspace,
    ):
        assert get_workspace_root() == mock_discord_workspace


def test_get_raw_dir_matches_boost_style_layout(settings, tmp_path):
    """Raw JSON lives under WORKSPACE_DIR/raw/discord_activity_tracker/."""
    settings.WORKSPACE_DIR = str(tmp_path)
    raw = get_raw_dir()
    assert raw == tmp_path / "raw" / "discord_activity_tracker"
    assert raw.is_dir()


def test_get_channel_raw_dir_nested(settings, tmp_path):
    settings.WORKSPACE_DIR = str(tmp_path)
    p = get_channel_raw_dir(4242, 9001)
    assert p == tmp_path / "raw" / "discord_activity_tracker" / "4242" / "9001"
    assert p.is_dir()


def test_get_server_dir(mock_discord_workspace):
    with patch(
        "discord_activity_tracker.workspace.get_workspace_path",
        return_value=mock_discord_workspace,
    ):
        p = get_server_dir(4242)
    assert p == mock_discord_workspace / "4242"
    assert p.is_dir()


def test_get_channel_json_path(mock_discord_workspace):
    with patch(
        "discord_activity_tracker.workspace.get_workspace_path",
        return_value=mock_discord_workspace,
    ):
        path = get_channel_json_path(1, 999)
    assert path.name == "999.json"
    assert path.parent.name == "channels"


def test_get_messages_json_path(mock_discord_workspace):
    with patch(
        "discord_activity_tracker.workspace.get_workspace_path",
        return_value=mock_discord_workspace,
    ):
        path = get_messages_json_path(1, 2, "2026-05-01")
    assert path.name == "2026-05-01.json"


def test_iter_existing_message_jsons_yields_files(mock_discord_workspace):
    with patch(
        "discord_activity_tracker.workspace.get_workspace_path",
        return_value=mock_discord_workspace,
    ):
        msg_dir = mock_discord_workspace / "7" / "messages" / "8"
        msg_dir.mkdir(parents=True)
        (msg_dir / "day.json").write_text("{}", encoding="utf-8")
        paths = list(iter_existing_message_jsons(7, 8))
    assert len(paths) == 1
    assert paths[0].name == "day.json"


def test_iter_existing_message_jsons_skips_appledouble_sidecars(mock_discord_workspace):
    with patch(
        "discord_activity_tracker.workspace.get_workspace_path",
        return_value=mock_discord_workspace,
    ):
        msg_dir = mock_discord_workspace / "7" / "messages" / "8"
        msg_dir.mkdir(parents=True)
        (msg_dir / "day.json").write_text("{}", encoding="utf-8")
        (msg_dir / "._day.json").write_bytes(b"\xb0")
        paths = list(iter_existing_message_jsons(7, 8))
    assert len(paths) == 1
    assert paths[0].name == "day.json"


def test_iter_existing_message_jsons_empty_when_missing(mock_discord_workspace):
    with patch(
        "discord_activity_tracker.workspace.get_workspace_path",
        return_value=mock_discord_workspace,
    ):
        assert list(iter_existing_message_jsons(99, 99)) == []
