"""Tests for backfill_300_file_commits management command."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from github_activity_tracker.models import (
    FileChangeStatus,
    GitCommit,
    GitCommitFileChange,
    GitHubFile,
)


@pytest.mark.django_db
def test_backfill_no_commits_at_300():
    out = StringIO()
    call_command("backfill_300_file_commits", stdout=out, verbosity=0)
    assert "No commits" in out.getvalue()


@pytest.mark.django_db
def test_backfill_dry_run_lists_commit(github_repository):
    repo = github_repository
    account = repo.owner_account
    commit = GitCommit.objects.create(
        repo=repo,
        account=account,
        commit_hash="c" * 40,
        comment="",
        commit_at=timezone.now(),
    )
    files = GitHubFile.objects.bulk_create(
        [GitHubFile(repo=repo, filename=f"path/{i}.txt") for i in range(300)]
    )
    GitCommitFileChange.objects.bulk_create(
        [
            GitCommitFileChange(
                commit=commit,
                github_file=f,
                status=FileChangeStatus.ADDED,
            )
            for f in files
        ]
    )

    out = StringIO()
    call_command(
        "backfill_300_file_commits",
        dry_run=True,
        stdout=out,
        verbosity=0,
    )
    assert "Would backfill" in out.getvalue()
    assert "Dry run" in out.getvalue()


@pytest.mark.django_db
@patch(
    "github_activity_tracker.management.commands.backfill_300_file_commits.big_commit.get_full_commit_files"
)
@patch(
    "github_activity_tracker.management.commands.backfill_300_file_commits._process_commit_files"
)
def test_backfill_updates_when_git_returns_files(
    mock_process,
    mock_get_files,
    github_repository,
):
    repo = github_repository
    account = repo.owner_account
    commit = GitCommit.objects.create(
        repo=repo,
        account=account,
        commit_hash="d" * 40,
        comment="",
        commit_at=timezone.now(),
    )
    files = GitHubFile.objects.bulk_create(
        [GitHubFile(repo=repo, filename=f"x/{i}.txt") for i in range(300)]
    )
    GitCommitFileChange.objects.bulk_create(
        [
            GitCommitFileChange(
                commit=commit,
                github_file=f,
                status=FileChangeStatus.MODIFIED,
            )
            for f in files
        ]
    )

    mock_get_files.return_value = [{"filename": "full.txt", "status": "added"}]

    out = StringIO()
    call_command(
        "backfill_300_file_commits",
        limit=1,
        stdout=out,
        verbosity=0,
    )
    mock_process.assert_called_once()
    assert "Updated" in out.getvalue() or "Done" in out.getvalue()
