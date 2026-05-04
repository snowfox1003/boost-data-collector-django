"""Tests for cppa_youtube_script_tracker.workspace."""

from unittest.mock import patch

import pytest

from cppa_youtube_script_tracker.workspace import (
    get_metadata_queue_path,
    get_raw_dir,
    get_raw_metadata_path,
    get_raw_transcripts_dir,
    get_transcript_path,
    get_workspace_root,
    iter_metadata_queue_jsons,
)


@pytest.fixture
def mock_root(tmp_path):
    root = tmp_path / "cppa_youtube_script_tracker"
    root.mkdir(parents=True)
    with patch(
        "cppa_youtube_script_tracker.workspace.get_workspace_path",
        return_value=root,
    ):
        yield root


def test_get_workspace_root(mock_root):
    assert get_workspace_root() == mock_root


def test_get_raw_dir_creates_nested(tmp_path):
    raw_target = tmp_path / "raw_sub"
    with patch(
        "cppa_youtube_script_tracker.workspace.get_workspace_path",
        return_value=raw_target,
    ):
        raw = get_raw_dir()
    assert raw == raw_target
    assert raw.is_dir()


def test_paths_under_workspace(mock_root):
    mq = get_metadata_queue_path("abc123")
    assert mq.name == "abc123.json"
    assert mq.parent.name == "metadata"

    rm = get_raw_metadata_path("xyz")
    assert rm.parent.name == "metadata"
    assert rm.name == "xyz.json"

    transcripts = get_raw_transcripts_dir()
    assert transcripts.name == "transcripts"
    tr = get_transcript_path("v1", lang="en")
    assert tr.name == "v1.en.vtt"


def test_iter_metadata_queue_jsons_skips_hidden(mock_root):
    meta = mock_root / "metadata"
    meta.mkdir(parents=True)
    (meta / "a.json").write_text("{}", encoding="utf-8")
    (meta / ".hidden.json").write_text("{}", encoding="utf-8")

    paths = list(iter_metadata_queue_jsons())
    assert paths == [meta / "a.json"]


def test_iter_metadata_queue_jsons_missing_dir(mock_root):
    assert mock_root.joinpath("metadata").is_dir() is False
    assert list(iter_metadata_queue_jsons()) == []
