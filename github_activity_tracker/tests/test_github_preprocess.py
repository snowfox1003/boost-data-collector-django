"""Tests for github_activity_tracker.preprocessors.github_preprocess."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from github_activity_tracker.preprocessors import github_preprocess as gp


MIN_ISSUE = {
    "issue_info": {
        "number": 1,
        "title": "Hi",
        "html_url": "https://github.com/o/r/issues/1",
        "body": "Hello world",
        "state": "open",
        "user": {"login": "alice"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    },
    "comments": [],
}

MIN_PR = {
    "pr_info": {
        "number": 2,
        "title": "PR title",
        "html_url": "https://github.com/o/r/pull/2",
        "body": "desc",
        "state": "open",
        "user": {"login": "bob"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    },
    "reviews": [],
    "comments": [],
}


def test_helpers_parse_and_timestamp():
    assert gp._parse_updated_at({}) is None
    assert gp._parse_updated_at({"updated_at": "not-a-date"}) is None
    dt = gp._parse_updated_at({"updated_at": "2024-06-01T12:00:00Z"})
    assert dt is not None
    assert dt.tzinfo == timezone.utc

    assert gp._to_timestamp("") == 0.0
    assert gp._to_timestamp("bad") == 0.0
    assert gp._to_timestamp("2024-01-01T00:00:00Z") > 0

    assert gp.get_ids_for_pinecone("r", "issue", 3) == "r:issue:3"


def test_iter_json_files_skips_bad_files(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    (tmp_path / "not_dict.json").write_text(json.dumps([1]), encoding="utf-8")
    files = list(gp._iter_json_files(tmp_path))
    assert len(files) == 1
    assert files[0][1] == {"a": 1}

    assert list(gp._iter_json_files(tmp_path / "missing")) == []


def test_build_issue_document_skips_invalid():
    assert gp.build_issue_document(Path("x.json"), {}, "r") is None
    assert gp.build_issue_document(Path("x.json"), {"issue_info": []}, "r") is None
    assert (
        gp.build_issue_document(
            Path("x.json"),
            {"issue_info": {"number": 1, "title": "t"}},
            "r",
        )
        is None
    )


def test_build_issue_and_pr_documents_ok():
    p = Path("1.json")
    doc_i = gp.build_issue_document(p, MIN_ISSUE, "r")
    assert doc_i is not None
    assert doc_i["metadata"]["type"] == "issue"

    doc_p = gp.build_pr_document(p, MIN_PR, "r")
    assert doc_p is not None
    assert doc_p["metadata"]["type"] == "pr"


def test_preprocess_issues_incremental_and_failed(tmp_path):
    raw_root = tmp_path / "raw" / "github_activity_tracker"
    issues_dir = raw_root / "boostorg" / "boost" / "issues"
    issues_dir.mkdir(parents=True)
    (issues_dir / "1.json").write_text(json.dumps(MIN_ISSUE), encoding="utf-8")

    future_sync = datetime(2099, 1, 1, tzinfo=timezone.utc)

    with patch("github_activity_tracker.workspace.get_workspace_path") as m:
        m.side_effect = lambda slug: tmp_path / slug

        docs_all, _ = gp.preprocess_issues("boostorg", "boost", [], final_sync_at=None)
        assert len(docs_all) == 1

        docs_skip, _ = gp.preprocess_issues(
            "boostorg", "boost", [], final_sync_at=future_sync
        )
        assert docs_skip == []

        docs_retry, _ = gp.preprocess_issues(
            "boostorg",
            "boost",
            ["boost:issue:1"],
            final_sync_at=future_sync,
        )
        assert len(docs_retry) == 1


def test_preprocess_prs_and_preprocess_all(tmp_path):
    raw_root = tmp_path / "raw" / "github_activity_tracker"
    prs_dir = raw_root / "boostorg" / "geometry" / "prs"
    prs_dir.mkdir(parents=True)
    (prs_dir / "2.json").write_text(json.dumps(MIN_PR), encoding="utf-8")

    with patch("github_activity_tracker.workspace.get_workspace_path") as m:
        m.side_effect = lambda slug: tmp_path / slug

        docs, _ = gp.preprocess_prs("boostorg", "geometry", [], None)
        assert len(docs) == 1

        all_docs, _ = gp.preprocess_all_prs("boostorg", [], None)
        assert len(all_docs) == 1

        (raw_root / "boostorg" / "wave" / "issues").mkdir(parents=True)
        (raw_root / "boostorg" / "wave" / "issues" / "1.json").write_text(
            json.dumps(MIN_ISSUE), encoding="utf-8"
        )
        merged, _ = gp.preprocess_all_issues("boostorg", [], None)
        assert len(merged) >= 1


def test_iter_raw_repos_empty_and_nonempty(tmp_path):
    with patch("github_activity_tracker.workspace.get_workspace_path") as m:
        m.side_effect = lambda slug: tmp_path / slug
        owner_dir = tmp_path / "raw" / "github_activity_tracker" / "solo"
        owner_dir.mkdir(parents=True)
        assert list(gp.iter_raw_repos("solo")) == []

        (owner_dir / "r1").mkdir()
        (owner_dir / "skip.txt").write_text("x", encoding="utf-8")
        assert list(gp.iter_raw_repos("solo")) == ["r1"]
