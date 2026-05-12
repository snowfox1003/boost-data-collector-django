"""Tests for boost_library_tracker management commands (run_boost_github_activity_tracker, backfill_file_renames)."""

import json
import logging
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError


ACTIVITY_CMD = "run_boost_github_activity_tracker"
BACKFILL_CMD = "backfill_file_renames"


# --- backfill_file_renames ---


@pytest.mark.django_db
def test_backfill_file_renames_workspace_missing():
    """When workspace/raw/github_activity_tracker/boostorg does not exist, command errors and exits."""
    with patch(
        "boost_library_tracker.management.commands.backfill_file_renames.Path"
    ) as mock_path_cls:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path_cls.return_value = mock_path

        out = StringIO()
        err = StringIO()
        call_command(BACKFILL_CMD, stdout=out, stderr=err)

    assert "not found" in out.getvalue() or "not found" in err.getvalue()


@pytest.mark.django_db
def test_backfill_file_renames_dry_run_lists_renames(tmp_path, github_repository):
    """With --dry-run, command scans commit JSONs and lists renames without DB changes."""

    # Create boostorg-like structure under tmp_path
    base = tmp_path / "boostorg"
    (base / "math" / "commits").mkdir(parents=True)
    commit_data = {
        "sha": "abc123",
        "files": [
            {
                "filename": "include/new.hpp",
                "previous_filename": "include/old.hpp",
                "status": "renamed",
            },
        ],
    }
    (base / "math" / "commits" / "abc123.json").write_text(
        json.dumps(commit_data), encoding="utf-8"
    )

    # github_repository is from github_activity_tracker fixtures; ensure owner is boostorg
    account = github_repository.owner_account
    account.username = "boostorg"
    account.save()
    github_repository.repo_name = "math"
    github_repository.save()

    def path_side_effect(first, *args):
        if first == "workspace/raw/github_activity_tracker/boostorg":
            return base
        return Path(first, *args)

    out = StringIO()
    err = StringIO()
    with patch(
        "boost_library_tracker.management.commands.backfill_file_renames.Path",
        side_effect=path_side_effect,
    ):
        call_command(BACKFILL_CMD, "--dry-run", stdout=out, stderr=err)

    out_str = out.getvalue()
    assert "Would link" in out_str or "include/old.hpp" in out_str
    assert "Dry run" in out_str


@pytest.mark.django_db
def test_backfill_file_renames_updates_db_and_reports_counts(
    tmp_path, github_repository
):
    """Command finds renames, updates previous_filename_id, and reports updated count."""
    base = tmp_path / "boostorg"
    (base / "math" / "commits").mkdir(parents=True)
    commit_data = {
        "sha": "def456",
        "files": [
            {
                "filename": "b.txt",
                "previous_filename": "a.txt",
                "status": "renamed",
            },
        ],
    }
    (base / "math" / "commits" / "def456.json").write_text(
        json.dumps(commit_data), encoding="utf-8"
    )

    account = github_repository.owner_account
    account.username = "boostorg"
    account.save()
    github_repository.repo_name = "math"
    github_repository.save()

    def path_side_effect(first, *args):
        if first == "workspace/raw/github_activity_tracker/boostorg":
            return base
        return Path(first, *args)

    out = StringIO()
    err = StringIO()
    with patch(
        "boost_library_tracker.management.commands.backfill_file_renames.Path",
        side_effect=path_side_effect,
    ):
        call_command(BACKFILL_CMD, stdout=out, stderr=err)

    out_str = out.getvalue()
    assert "updated" in out_str.lower() or "1 " in out_str

    from github_activity_tracker.models import GitHubFile

    new_file = GitHubFile.objects.get(repo=github_repository, filename="b.txt")
    old_file = GitHubFile.objects.get(repo=github_repository, filename="a.txt")
    assert new_file.previous_filename_id == old_file.id


@pytest.mark.django_db
def test_backfill_file_renames_failed_count_and_not_linked_list(
    tmp_path, github_repository
):
    """When a rename update fails, command reports failed count and lists not linked."""
    base = tmp_path / "boostorg"
    (base / "math" / "commits").mkdir(parents=True)
    commit_data = {
        "sha": "failsha",
        "files": [
            {
                "filename": "fail_new.txt",
                "previous_filename": "fail_old.txt",
                "status": "renamed",
            },
        ],
    }
    (base / "math" / "commits" / "failsha.json").write_text(
        json.dumps(commit_data), encoding="utf-8"
    )

    account = github_repository.owner_account
    account.username = "boostorg"
    account.save()
    github_repository.repo_name = "math"
    github_repository.save()

    def path_side_effect(first, *args):
        if first == "workspace/raw/github_activity_tracker/boostorg":
            return base
        return Path(first, *args)

    out = StringIO()
    err = StringIO()
    with (
        patch(
            "boost_library_tracker.management.commands.backfill_file_renames.Path",
            side_effect=path_side_effect,
        ),
        patch(
            "boost_library_tracker.management.commands.backfill_file_renames.set_github_file_previous_filename",
            side_effect=RuntimeError("DB error"),
        ),
    ):
        call_command(BACKFILL_CMD, stdout=out, stderr=err)

    out_str = out.getvalue()
    err_str = err.getvalue()
    combined = out_str + err_str
    assert "failed" in combined
    assert "Not linked" in combined
    assert "fail_old.txt" in combined and "fail_new.txt" in combined


@pytest.mark.django_db
def test_run_boost_github_activity_tracker_dry_run_lists_repos(caplog):
    """Dry-run calls sync preview (repo list) without sync_github; progress is logged."""
    mock_client = MagicMock()
    mock_client.get_file_content.return_value = (b"", "utf-8")
    mock_account = MagicMock()
    mock_account.username = "boostorg"
    caplog.set_level(logging.INFO)
    with (
        patch(
            "boost_library_tracker.management.commands.run_boost_github_activity_tracker.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_library_tracker.management.commands.run_boost_github_activity_tracker.get_or_create_owner_account",
            return_value=mock_account,
        ),
        patch(
            "boost_library_tracker.management.commands.run_boost_github_activity_tracker.sync_github",
        ) as sync_mock,
    ):
        call_command(ACTIVITY_CMD, "--dry-run", stdout=StringIO(), stderr=StringIO())
    sync_mock.assert_not_called()
    combined = caplog.text.lower()
    assert "would sync" in combined or "repo" in combined


@pytest.mark.django_db
def test_run_boost_github_activity_tracker_command_error_when_scraping_token_invalid():
    with patch(
        "boost_library_tracker.management.commands.run_boost_github_activity_tracker.validate_github_token_for_use",
        side_effect=ValueError("GitHub scraping token is invalid"),
    ):
        with pytest.raises(CommandError, match="GitHub scraping token is invalid"):
            call_command(
                ACTIVITY_CMD, "--dry-run", stdout=StringIO(), stderr=StringIO()
            )


@pytest.mark.django_db
def test_run_boost_github_activity_tracker_invalid_since_errors():
    """Invalid --since raises CommandError; fetch task is not run."""
    mock_client = MagicMock()
    mock_client.get_file_content.return_value = (b"", "utf-8")
    mock_account = MagicMock()
    mock_account.username = "boostorg"
    with (
        patch(
            "boost_library_tracker.management.commands.run_boost_github_activity_tracker.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_library_tracker.management.commands.run_boost_github_activity_tracker.get_or_create_owner_account",
            return_value=mock_account,
        ),
        patch(
            "boost_library_tracker.management.commands.run_boost_github_activity_tracker.sync_github",
        ),
        patch(
            "boost_library_tracker.management.commands.run_boost_github_activity_tracker.task_fetch_github_activity",
        ) as task_mock,
    ):
        with pytest.raises(CommandError, match="Invalid ISO datetime"):
            call_command(
                ACTIVITY_CMD,
                "--since=not-a-date",
                "--dry-run",
                stdout=StringIO(),
                stderr=StringIO(),
            )
    task_mock.assert_not_called()


@pytest.mark.django_db
def test_check_new_boost_release_exits_zero_when_release_found():
    """Exit code 0 when has_new_boost_release returns True."""
    from io import StringIO

    with patch(
        "boost_library_tracker.management.commands.check_new_boost_release.has_new_boost_release",
        return_value=True,
    ):
        with pytest.raises(SystemExit) as excinfo:
            call_command(
                "check_new_boost_release",
                stdout=StringIO(),
                stderr=StringIO(),
            )
    assert excinfo.value.code == 0


@pytest.mark.django_db
def test_check_new_boost_release_exits_one_when_none():
    """Exit code 1 when no new release."""
    from io import StringIO

    with patch(
        "boost_library_tracker.management.commands.check_new_boost_release.has_new_boost_release",
        return_value=False,
    ):
        with pytest.raises(SystemExit) as excinfo:
            call_command(
                "check_new_boost_release",
                stdout=StringIO(),
                stderr=StringIO(),
            )
    assert excinfo.value.code == 1


@pytest.mark.django_db
def test_backfill_repo_filter_not_present(tmp_path, monkeypatch):
    base = tmp_path / "workspace" / "raw" / "github_activity_tracker" / "boostorg"
    base.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    out = StringIO()
    call_command(BACKFILL_CMD, "--repo=missing-repo", stdout=out)
    assert "not found" in out.getvalue().lower()


@pytest.mark.django_db
def test_backfill_skips_repo_without_commits_dir(tmp_path, monkeypatch):
    repo_root = (
        tmp_path / "workspace" / "raw" / "github_activity_tracker" / "boostorg" / "math"
    )
    repo_root.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    out = StringIO()
    call_command(BACKFILL_CMD, stdout=out)
    assert "no commits directory" in out.getvalue().lower()


@pytest.mark.django_db
def test_backfill_dry_run_prints_would_link(
    tmp_path, monkeypatch, github_account, github_repository
):
    github_account.username = "boostorg"
    github_account.save()
    github_repository.repo_name = "math"
    github_repository.owner_account = github_account
    github_repository.save()

    commits = (
        tmp_path
        / "workspace"
        / "raw"
        / "github_activity_tracker"
        / "boostorg"
        / "math"
        / "commits"
    )
    commits.mkdir(parents=True)
    sha_file = commits / "abcd.json"
    sha_file.write_text(
        json.dumps(
            {
                "sha": "abcd",
                "files": [
                    {
                        "filename": "new.txt",
                        "previous_filename": "old.txt",
                        "status": "renamed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    out = StringIO()
    call_command(BACKFILL_CMD, "--dry-run", stdout=out)
    assert "Would link" in out.getvalue()


@pytest.mark.django_db
def test_backfill_skips_workspace_repo_missing_from_db(tmp_path, monkeypatch):
    commits = (
        tmp_path
        / "workspace"
        / "raw"
        / "github_activity_tracker"
        / "boostorg"
        / "ghostlib"
        / "commits"
    )
    commits.mkdir(parents=True)
    (commits / "z.json").write_text(
        json.dumps({"sha": "z", "files": []}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    out = StringIO()
    call_command(BACKFILL_CMD, stdout=out)
    assert "not found in database" in out.getvalue().lower()


@pytest.mark.django_db
def test_backfill_reports_bad_commit_json(
    tmp_path, monkeypatch, github_account, github_repository
):
    github_account.username = "boostorg"
    github_account.save()
    github_repository.repo_name = "brokenjson"
    github_repository.owner_account = github_account
    github_repository.save()

    commits = (
        tmp_path
        / "workspace"
        / "raw"
        / "github_activity_tracker"
        / "boostorg"
        / "brokenjson"
        / "commits"
    )
    commits.mkdir(parents=True)
    (commits / "bad.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    out = StringIO()
    call_command(BACKFILL_CMD, stdout=out)
    assert "Error processing bad.json" in out.getvalue()
