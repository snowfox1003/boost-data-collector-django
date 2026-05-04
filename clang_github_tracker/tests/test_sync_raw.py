"""Tests for clang_github_tracker.sync_raw."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import json

import pytest

from clang_github_tracker import sync_raw


def test_ensure_utc():
    naive = datetime(2024, 1, 2, 3, 4, 5)
    u = sync_raw._ensure_utc(naive)
    assert u.tzinfo == timezone.utc
    assert sync_raw._ensure_utc(None) is None


def test_valid_positive_issue_number():
    assert sync_raw._valid_positive_issue_number(3) is True
    assert sync_raw._valid_positive_issue_number(0) is False
    assert sync_raw._valid_positive_issue_number(True) is False
    assert sync_raw._valid_positive_issue_number("1") is False


def test_commit_date_extracts():
    d = sync_raw.commit_date({"commit": {"author": {"date": "2024-01-01T00:00:00Z"}}})
    assert d is not None
    assert sync_raw.commit_date({}) is None


def test_write_staging_json(tmp_path):
    p = tmp_path / "sub" / "f.json"
    sync_raw._write_staging_json(p, {"a": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}


@pytest.mark.django_db
def test_promote_commit_missing_sha_unlinks(tmp_path):
    sp = tmp_path / "c.json"
    sync_raw._write_staging_json(sp, {})
    assert sp.exists()
    assert sync_raw._promote_commit_staging("o", "r", sp, {}) is False
    assert not sp.exists()


@pytest.mark.django_db
def test_promote_commit_upsert_failure_keeps_staging(tmp_path):
    sp = tmp_path / "keep.json"
    data = {"sha": "abc", "commit": {"author": {"date": "2024-01-01T00:00:00Z"}}}
    sync_raw._write_staging_json(sp, data)
    with patch.object(
        sync_raw.clang_services, "upsert_commit", side_effect=RuntimeError("db")
    ):
        assert sync_raw._promote_commit_staging("o", "r", sp, data) is False
    assert sp.exists()


@pytest.mark.django_db
def test_promote_commit_raw_failure_keeps_staging(tmp_path):
    sp = tmp_path / "x.json"
    data = {"sha": "deadbeef", "commit": {"author": {"date": "2024-01-01T00:00:00Z"}}}
    sync_raw._write_staging_json(sp, data)
    with patch.object(sync_raw.clang_services, "upsert_commit", return_value=None):
        with patch.object(
            sync_raw, "save_commit_raw_source", side_effect=OSError("disk")
        ):
            assert (
                sync_raw._promote_commit_staging("llvm", "llvm-project", sp, data)
                is False
            )
    assert sp.exists()


@pytest.mark.django_db
def test_promote_issue_invalid_number(tmp_path):
    sp = tmp_path / "i.json"
    sync_raw._write_staging_json(sp, {"number": None})
    assert sync_raw._promote_issue_staging("o", "r", sp, {}) is False
    assert not sp.exists()


@pytest.mark.django_db
def test_promote_pr_invalid_number(tmp_path):
    sp = tmp_path / "p.json"
    sync_raw._write_staging_json(sp, {"number": -1})
    assert sync_raw._promote_pr_staging("o", "r", sp, {}) is False


def test_process_pending_skips_bad_json(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sync_raw,
        "iter_existing_commit_jsons",
        lambda o, r: [tmp_path / "bad.json"],
    )
    monkeypatch.setattr(sync_raw, "iter_existing_issue_jsons", lambda o, r: [])
    monkeypatch.setattr(sync_raw, "iter_existing_pr_jsons", lambda o, r: [])
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    c, i, p = sync_raw.process_pending_clang_staging("o", "r")
    assert c == 0 and i == [] and p == []


@pytest.mark.django_db
def test_sync_clang_github_activity_promotes_then_raises_rate_limit():
    commit = {"sha": "abc123", "commit": {"author": {"date": "2024-01-01T00:00:00Z"}}}

    def fake_commits(client, owner, repo, sc, ed):
        yield commit

    def fake_issues(*_a, **_k):
        yield from ()

    with patch.object(sync_raw, "get_github_client", return_value=MagicMock()):
        with patch.object(
            sync_raw, "process_pending_clang_staging", return_value=(0, [], [])
        ):
            with patch.object(
                sync_raw.fetcher, "fetch_commits_from_github", fake_commits
            ):
                with patch.object(
                    sync_raw.fetcher,
                    "fetch_issues_and_prs_from_github",
                    fake_issues,
                ):
                    with patch.object(
                        sync_raw, "_promote_commit_staging", return_value=True
                    ):
                        with patch.object(sync_raw, "_write_staging_json"):
                            with patch.object(
                                sync_raw,
                                "get_commit_json_path",
                                return_value=Path("x.json"),
                            ):
                                c, _, _ = sync_raw.sync_clang_github_activity()
    assert c >= 1


@pytest.mark.django_db
def test_promote_commit_success_removes_staging(tmp_path):
    sp = tmp_path / "c.json"
    data = {"sha": "deadbeef", "commit": {"author": {"date": "2024-01-01T00:00:00Z"}}}
    sync_raw._write_staging_json(sp, data)
    with patch.object(sync_raw.clang_services, "upsert_commit", return_value=None):
        with patch.object(sync_raw, "save_commit_raw_source", return_value=None):
            assert (
                sync_raw._promote_commit_staging("llvm", "llvm-project", sp, data)
                is True
            )
    assert not sp.exists()


@pytest.mark.django_db
def test_promote_issue_success(tmp_path):
    sp = tmp_path / "i.json"
    item = {
        "number": 42,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }
    sync_raw._write_staging_json(sp, item)
    with patch.object(sync_raw.clang_services, "upsert_issue_item", return_value=None):
        with patch.object(sync_raw, "save_issue_raw_source", return_value=None):
            assert (
                sync_raw._promote_issue_staging("llvm", "llvm-project", sp, item)
                is True
            )


@pytest.mark.django_db
def test_promote_pr_success(tmp_path):
    sp = tmp_path / "p.json"
    item = {
        "number": 99,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }
    sync_raw._write_staging_json(sp, item)
    with patch.object(sync_raw.clang_services, "upsert_issue_item", return_value=None):
        with patch.object(sync_raw, "save_pr_raw_source", return_value=None):
            assert (
                sync_raw._promote_pr_staging("llvm", "llvm-project", sp, item) is True
            )


def test_sync_propagates_connection_exception():
    with patch.object(sync_raw, "get_github_client", return_value=MagicMock()):
        with patch.object(
            sync_raw, "process_pending_clang_staging", return_value=(0, [], [])
        ):
            with patch.object(
                sync_raw.fetcher,
                "fetch_commits_from_github",
                side_effect=sync_raw.ConnectionException("rate"),
            ):
                with pytest.raises(sync_raw.ConnectionException):
                    sync_raw.sync_clang_github_activity()
