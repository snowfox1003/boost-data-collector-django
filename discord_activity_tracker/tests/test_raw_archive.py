"""Tests for sync/raw_archive.py."""

from __future__ import annotations

import json
from pathlib import Path

from discord_activity_tracker.sync.raw_archive import (
    merge_exporter_json,
    message_utc_date_str,
)


def _msg(mid: str, ts: str) -> dict:
    return {"id": mid, "timestamp": ts, "content": f"msg-{mid}"}


def _envelope(*messages: dict) -> dict:
    return {
        "guild": {"id": "1", "name": "G"},
        "channel": {"id": "2", "name": "c"},
        "messages": list(messages),
    }


def test_message_utc_date_str_parses_offset():
    assert message_utc_date_str(_msg("1", "2026-06-02T22:00:00+00:00")) == "2026-06-02"


def test_merge_exporter_json_creates_new_file(tmp_path: Path):
    dest = tmp_path / "2026-06-02.json"
    incoming = _envelope(_msg("100", "2026-06-02T10:00:00Z"))
    count = merge_exporter_json(dest, incoming, day="2026-06-02")
    assert count == 1
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert len(data["messages"]) == 1
    assert data["messages"][0]["id"] == "100"


def test_merge_exporter_json_appends_new_message_same_day(tmp_path: Path):
    dest = tmp_path / "2026-06-02.json"
    first = _envelope(_msg("100", "2026-06-02T10:00:00Z"))
    merge_exporter_json(dest, first, day="2026-06-02")
    second = _envelope(_msg("101", "2026-06-02T23:00:00Z"))
    count = merge_exporter_json(dest, second, day="2026-06-02")
    assert count == 2
    data = json.loads(dest.read_text(encoding="utf-8"))
    ids = [m["id"] for m in data["messages"]]
    assert ids == ["100", "101"]


def test_merge_exporter_json_updates_same_id(tmp_path: Path):
    dest = tmp_path / "2026-06-02.json"
    merge_exporter_json(
        dest,
        _envelope(_msg("100", "2026-06-02T10:00:00Z")),
        day="2026-06-02",
    )
    merge_exporter_json(
        dest,
        _envelope({**_msg("100", "2026-06-02T10:00:00Z"), "content": "edited"}),
        day="2026-06-02",
    )
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "edited"


def test_merge_exporter_json_filters_wrong_day(tmp_path: Path):
    dest = tmp_path / "2026-06-02.json"
    incoming = _envelope(
        _msg("100", "2026-06-02T10:00:00Z"),
        _msg("200", "2026-06-03T01:00:00Z"),
    )
    count = merge_exporter_json(dest, incoming, day="2026-06-02")
    assert count == 1
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert [m["id"] for m in data["messages"]] == ["100"]


def test_merge_exporter_json_refreshes_date_range(tmp_path: Path):
    dest = tmp_path / "2026-06-02.json"
    merge_exporter_json(
        dest,
        _envelope(
            _msg("100", "2026-06-02T10:00:00Z"),
            _msg("101", "2026-06-02T23:00:00Z"),
        ),
        day="2026-06-02",
    )
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "dateRange" in data
    assert data["dateRange"]["after"].startswith("2026-06-02")
    assert data["dateRange"]["before"].startswith("2026-06-02")
    assert "exportedAt" in data
