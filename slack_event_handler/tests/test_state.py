"""Tests for slack_event_handler.utils.state."""

import threading
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


def test_get_lock_file_path_appends_lock_suffix(data_dir):
    state_path = str(data_dir / "state.json")
    with patch.object(state_mod, "_get_state_file_path", return_value=state_path):
        assert state_mod._get_lock_file_path(None) == f"{state_path}.lock"


def test_get_lock_file_path_team_id(data_dir):
    state_path = str(data_dir / "state_T9.json")
    with patch.object(state_mod, "_get_state_file_path", return_value=state_path):
        assert state_mod._get_lock_file_path("T9") == f"{state_path}.lock"


def test_thread_lock_for_same_lock_file_path(tmp_path):
    root = tmp_path / "slack_event_handler"
    root.mkdir(parents=True)
    with patch("slack_event_handler.workspace.get_workspace_root", return_value=root):
        lock_a = state_mod._thread_lock_for("T/1")
        lock_b = state_mod._thread_lock_for("T?1")
    assert lock_a is lock_b


def test_state_file_lock_blocks_until_released(data_dir):
    state_path = str(data_dir / "state.json")
    lock_path = f"{state_path}.lock"
    holder_ready = threading.Event()
    holder_release = threading.Event()
    second_acquired = threading.Event()

    def hold_lock():
        with patch.object(state_mod, "_get_lock_file_path", return_value=lock_path):
            with state_mod.state_file_lock(None):
                holder_ready.set()
                holder_release.wait(timeout=5)

    def try_lock():
        holder_ready.wait(timeout=5)
        with patch.object(state_mod, "_get_lock_file_path", return_value=lock_path):
            with state_mod.state_file_lock(None):
                second_acquired.set()

    holder = threading.Thread(target=hold_lock)
    waiter = threading.Thread(target=try_lock)
    holder.start()
    waiter.start()
    holder_ready.wait(timeout=5)
    assert not second_acquired.is_set()
    holder_release.set()
    waiter.join(timeout=5)
    holder.join(timeout=5)
    assert second_acquired.is_set()


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
