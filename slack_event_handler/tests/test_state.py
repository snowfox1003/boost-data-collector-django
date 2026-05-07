"""Tests for slack_event_handler.utils.state."""

from unittest.mock import patch

import pytest

from slack_event_handler.utils import state as state_mod


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir(parents=True)
    return d


def test_load_state_missing_file_returns_default(data_dir):
    with patch(
        "slack_event_handler.workspace.get_workspace_root",
        return_value=data_dir.parent,
    ):
        with patch.object(
            state_mod, "_get_state_file_path", return_value=str(data_dir / "state.json")
        ):
            s = state_mod.load_state(None)
    assert s == {"postedAt": [], "queue": []}


def test_load_state_corrupt_json_quarantines_and_returns_default(data_dir, monkeypatch):
    bad = data_dir / "state.json"
    bad.write_text("{not json", encoding="utf-8")

    with patch(
        "slack_event_handler.workspace.get_workspace_root",
        return_value=data_dir.parent,
    ):
        with patch.object(state_mod, "_get_state_file_path", return_value=str(bad)):
            monkeypatch.setattr(state_mod.time, "time", lambda: 12345.0)
            s = state_mod.load_state(None)
    assert s == {"postedAt": [], "queue": []}
    quarantined = list(data_dir.glob("state.json.corrupt.*"))
    assert len(quarantined) == 1


def test_save_state_roundtrip(data_dir):
    path = data_dir / "state.json"
    payload = {"postedAt": [1.0, 2.0], "queue": [{"jobId": "x"}]}

    with patch(
        "slack_event_handler.workspace.get_workspace_root",
        return_value=data_dir.parent,
    ):
        with patch.object(state_mod, "_get_state_file_path", return_value=str(path)):
            state_mod.save_state(payload, None)
            loaded = state_mod.load_state(None)
    assert loaded["postedAt"] == [1.0, 2.0]
    assert loaded["queue"][0]["jobId"] == "x"


def test_get_state_file_path_team_id_sanitized(tmp_path):
    root = tmp_path / "slack_event_handler"
    root.mkdir(parents=True)
    with patch("slack_event_handler.workspace.get_workspace_root", return_value=root):
        p = state_mod._get_state_file_path("T01234/whee")
    norm = p.replace("\\", "/")
    assert "state_T01234_whee.json" in norm
    assert "/data/" in norm or norm.endswith("/data/state_T01234_whee.json")


def test_sanitize_team_id_empty_returns_default():
    assert state_mod._sanitize_team_id_for_path("") == "default"


def test_load_state_corrupt_json_quarantine_oserror_fallback(data_dir, monkeypatch):
    bad = data_dir / "state.json"
    bad.write_text("{not json", encoding="utf-8")

    def boom_replace(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(state_mod.os, "replace", boom_replace)

    with patch(
        "slack_event_handler.workspace.get_workspace_root",
        return_value=data_dir.parent,
    ):
        with patch.object(state_mod, "_get_state_file_path", return_value=str(bad)):
            monkeypatch.setattr(state_mod.time, "time", lambda: 999.0)
            s = state_mod.load_state(None)
    assert s == {"postedAt": [], "queue": []}
