"""Tests for backfill_clang_github_tracker."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from clang_github_tracker.models import ClangGithubCommit, ClangGithubIssueItem
from clang_github_tracker.workspace import OWNER, REPO


@pytest.mark.django_db
def test_backfill_from_raw(tmp_path, monkeypatch):
    root = tmp_path / "raw" / OWNER / REPO
    (root / "issues").mkdir(parents=True)
    (root / "prs").mkdir(parents=True)
    (root / "commits").mkdir(parents=True)
    (root / "issues" / "3.json").write_text(
        json.dumps(
            {
                "issue_info": {
                    "number": 3,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-02T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "prs" / "4.json").write_text(
        json.dumps(
            {
                "pr_info": {
                    "number": 4,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-02T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    sha = "b" * 40
    (root / "commits" / f"{sha}.json").write_text(
        json.dumps(
            {
                "sha": sha,
                "commit": {
                    "author": {"date": "2024-05-01T00:00:00Z"},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "clang_github_tracker.management.commands.backfill_clang_github_tracker.get_raw_repo_dir",
        lambda *a, **k: root,
    )
    call_command("backfill_clang_github_tracker")
    assert ClangGithubIssueItem.objects.filter(number=3, is_pull_request=False).exists()
    assert ClangGithubIssueItem.objects.filter(number=4, is_pull_request=True).exists()
    assert ClangGithubCommit.objects.filter(sha=sha).exists()


@pytest.mark.django_db
def test_backfill_raises_when_raw_root_missing(tmp_path, monkeypatch):
    missing = tmp_path / "nope"
    monkeypatch.setattr(
        "clang_github_tracker.management.commands.backfill_clang_github_tracker.get_raw_repo_dir",
        lambda *a, **k: missing,
    )
    with pytest.raises(CommandError, match="Raw repo dir missing"):
        call_command("backfill_clang_github_tracker")


@pytest.mark.django_db
def test_backfill_skips_bad_commit_json_and_invalid_sha(tmp_path, monkeypatch):
    root = tmp_path / "raw" / OWNER / REPO
    (root / "commits").mkdir(parents=True)
    (root / "commits" / "bad.json").write_text("{", encoding="utf-8")
    (root / "commits" / "short.json").write_text(
        json.dumps({"sha": "tooshort", "commit": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "clang_github_tracker.management.commands.backfill_clang_github_tracker.get_raw_repo_dir",
        lambda *a, **k: root,
    )
    call_command("backfill_clang_github_tracker")
    assert ClangGithubCommit.objects.count() == 0


@pytest.mark.django_db
def test_backfill_commit_chunk_flush(monkeypatch, tmp_path):
    import clang_github_tracker.management.commands.backfill_clang_github_tracker as bf

    monkeypatch.setattr(bf, "_RAW_CHUNK_EVERY", 2)
    root = tmp_path / "raw" / OWNER / REPO
    (root / "commits").mkdir(parents=True)
    for i in range(3):
        sha = f"{i:040x}"
        (root / "commits" / f"{sha}.json").write_text(
            json.dumps(
                {
                    "sha": sha,
                    "commit": {"author": {"date": "2024-05-01T00:00:00Z"}},
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(
        "clang_github_tracker.management.commands.backfill_clang_github_tracker.get_raw_repo_dir",
        lambda *a, **k: root,
    )
    call_command("backfill_clang_github_tracker")
    assert ClangGithubCommit.objects.count() == 3
