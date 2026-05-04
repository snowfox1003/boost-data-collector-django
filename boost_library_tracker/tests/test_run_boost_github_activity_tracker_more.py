"""Extra coverage for run_boost_github_activity_tracker helpers and branches."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.core.management import CommandError, call_command
from django.test.utils import override_settings

from boost_library_tracker.management.commands import (
    run_boost_github_activity_tracker as gh_cmd,
)
from boost_library_tracker.management.commands.run_boost_github_activity_tracker import (
    RateLimitException,
)


def test_parse_gitmodules_owner_repo_https_and_relative():
    text = """
[submodule "libs/foo"]
\tpath = libs/foo
\turl = https://github.com/boostorg/foo.git
[submodule "libs/bar"]
\tpath = libs/bar
\turl = ../bar
"""
    pairs = gh_cmd._parse_gitmodules_owner_repo(text)
    assert ("boostorg", "foo") in pairs
    assert ("boostorg", "bar") in pairs


@override_settings(
    BOOST_LIBRARY_TRACKER_REPO_OWNER="", BOOST_LIBRARY_TRACKER_REPO_NAME=""
)
def test_markdown_export_repo_config_unconfigured():
    assert gh_cmd._markdown_export_repo_config() is None


@override_settings(
    BOOST_LIBRARY_TRACKER_REPO_OWNER="o",
    BOOST_LIBRARY_TRACKER_REPO_NAME="r",
    BOOST_LIBRARY_TRACKER_REPO_BRANCH="",
)
def test_markdown_export_repo_config_defaults_branch():
    owner, repo, branch = gh_cmd._markdown_export_repo_config()
    assert (owner, repo, branch) == ("o", "r", gh_cmd.DEFAULT_MARKDOWN_REPO_BRANCH)


def test_generate_markdown_for_synced_skips_empty_numbers(tmp_path):
    synced = [
        ("boostorg", "math", None, {"issues": [], "pull_requests": []}),
    ]
    out = gh_cmd._generate_markdown_for_synced(synced, tmp_path)
    assert out == {}


def test_generate_markdown_for_synced_writes(tmp_path):
    synced = [
        ("boostorg", "boost", None, {"issues": [1], "pull_requests": [2]}),
    ]
    with patch(
        "boost_library_tracker.management.commands.run_boost_github_activity_tracker.write_md_files",
        return_value={"a.md": "/local"},
    ):
        out = gh_cmd._generate_markdown_for_synced(synced, tmp_path)
    assert out == {"a.md": "/local"}


def test_push_markdown_no_settings_logs(tmp_path, caplog):
    caplog.set_level("ERROR")
    with override_settings(
        BOOST_LIBRARY_TRACKER_REPO_OWNER="", BOOST_LIBRARY_TRACKER_REPO_NAME=""
    ):
        gh_cmd._push_markdown_to_github(tmp_path, {"x": "y"})
    assert any("not configured" in r.message for r in caplog.records)


def test_push_markdown_upload_failure_raises(tmp_path):
    with override_settings(
        BOOST_LIBRARY_TRACKER_REPO_OWNER="o",
        BOOST_LIBRARY_TRACKER_REPO_NAME="r",
    ), patch.object(gh_cmd, "get_github_token", return_value="t"), patch.object(
        gh_cmd, "detect_renames_from_dirs", return_value=[]
    ), patch.object(
        gh_cmd,
        "upload_folder_to_github",
        return_value={"success": False, "message": "nope"},
    ):
        with pytest.raises(CommandError, match="nope"):
            gh_cmd._push_markdown_to_github(tmp_path, {"f.md": "p"})


def test_push_markdown_success_cleans_files(tmp_path):
    dirty = tmp_path / "keep.txt"
    dirty.write_text("z", encoding="utf-8")
    with override_settings(
        BOOST_LIBRARY_TRACKER_REPO_OWNER="o",
        BOOST_LIBRARY_TRACKER_REPO_NAME="r",
    ), patch.object(gh_cmd, "get_github_token", return_value="t"), patch.object(
        gh_cmd, "detect_renames_from_dirs", return_value=[]
    ), patch.object(
        gh_cmd,
        "upload_folder_to_github",
        return_value={"success": True},
    ):
        gh_cmd._push_markdown_to_github(tmp_path, {"f.md": "p"})
    assert not dirty.exists()


def test_push_markdown_deletes_stale_renamed_locals(tmp_path):
    stale = tmp_path / "gone.md"
    stale.write_text("old", encoding="utf-8")
    with override_settings(
        BOOST_LIBRARY_TRACKER_REPO_OWNER="o",
        BOOST_LIBRARY_TRACKER_REPO_NAME="r",
    ), patch.object(gh_cmd, "get_github_token", return_value="t"), patch.object(
        gh_cmd, "detect_renames_from_dirs", return_value=["gone.md"]
    ), patch.object(
        gh_cmd,
        "upload_folder_to_github",
        return_value={"success": True},
    ):
        gh_cmd._push_markdown_to_github(tmp_path, {"n.md": "p"})
    assert not stale.exists()


@pytest.mark.django_db
def test_task_fetch_logs_date_window(caplog, github_account):
    github_account.username = "boostorg"
    github_account.save()
    caplog.set_level(logging.INFO)
    mock_client = MagicMock()
    mock_client.get_file_content.return_value = (b"", "utf-8")
    start = datetime(2019, 1, 1)
    end = datetime(2019, 2, 1)
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        return_value=github_account,
    ):
        gh_cmd.task_fetch_github_activity(dry_run=True, start_date=start, end_date=end)
    messages = " ".join(r.message for r in caplog.records)
    assert "2019-01-01" in messages or "sync from" in messages


@pytest.mark.django_db
def test_task_fetch_gitmodules_http_error_non404_raises(github_account):
    github_account.username = "boostorg"
    github_account.save()

    def raise_500(*_a, **_k):
        resp = MagicMock()
        resp.status_code = 500
        err = requests.exceptions.HTTPError()
        err.response = resp
        raise err

    mock_client = MagicMock()
    mock_client.get_file_content.side_effect = raise_500
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        return_value=github_account,
    ):
        with pytest.raises(requests.exceptions.HTTPError):
            gh_cmd.task_fetch_github_activity(dry_run=True)


@pytest.mark.django_db
def test_task_fetch_from_repo_finds_submodule(caplog, github_account):
    github_account.username = "boostorg"
    github_account.save()
    caplog.set_level(logging.INFO)
    gm = (
        b'[submodule "timer"]\n\tpath = libs/timer\n'
        b"\turl = https://github.com/boostorg/timer.git\n"
    )
    mock_client = MagicMock()
    mock_client.get_file_content.return_value = (gm, "utf-8")
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        return_value=github_account,
    ):
        gh_cmd.task_fetch_github_activity(dry_run=True, from_repo="timer")
    assert any("starting from" in r.message.lower() for r in caplog.records)


def test_run_pinecone_sync_short_circuits():
    gh_cmd._run_pinecone_sync("", "ns", "pkg.fn")
    gh_cmd._run_pinecone_sync("app", "", "pkg.fn")


def test_run_pinecone_sync_call_command_warning(caplog):
    caplog.set_level("WARNING")
    with patch(
        "boost_library_tracker.management.commands.run_boost_github_activity_tracker.call_command",
        side_effect=RuntimeError("no sync cmd"),
    ):
        gh_cmd._run_pinecone_sync("app", "ns", "pkg.fn")
    assert any("Pinecone sync skipped" in r.message for r in caplog.records)


def test_task_pinecone_sync_dry_run(caplog):
    caplog.set_level("INFO")
    gh_cmd.task_pinecone_sync(dry_run=True)
    assert any("dry-run would run Pinecone" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_task_fetch_dry_run_lists_submodules(caplog, github_account):
    caplog.set_level("INFO")
    gm = b'[submodule "x"]\n\tpath = x\n\turl = https://github.com/boostorg/timer.git\n'
    mock_client = MagicMock()
    mock_client.get_file_content.return_value = (gm, "utf-8")
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        return_value=github_account,
    ):
        gh_cmd.task_fetch_github_activity(dry_run=True)
    assert any("dry-run would sync" in r.message.lower() for r in caplog.records)


@pytest.mark.django_db
def test_task_fetch_gitmodules_http404(caplog, github_account):
    caplog.set_level("DEBUG")

    def raise_404(*_a, **_k):
        resp = MagicMock()
        resp.status_code = 404
        err = requests.exceptions.HTTPError()
        err.response = resp
        raise err

    mock_client = MagicMock()
    mock_client.get_file_content.side_effect = raise_404
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        return_value=github_account,
    ):
        gh_cmd.task_fetch_github_activity(dry_run=True)
    assert any(".gitmodules" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_task_fetch_gitmodules_generic_warning(caplog, github_account):
    caplog.set_level("WARNING")
    mock_client = MagicMock()
    mock_client.get_file_content.side_effect = RuntimeError("net")
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        return_value=github_account,
    ):
        gh_cmd.task_fetch_github_activity(dry_run=True)
    assert any("Could not fetch .gitmodules" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_task_fetch_from_repo_unknown_warns(caplog, github_account):
    caplog.set_level("WARNING")
    mock_client = MagicMock()
    mock_client.get_file_content.return_value = (b"", "utf-8")
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        return_value=github_account,
    ):
        gh_cmd.task_fetch_github_activity(dry_run=True, from_repo="missing-lib")
    assert any("No submodule" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_task_fetch_owner_account_rate_limit_raises():
    mock_client = MagicMock()
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd,
        "get_or_create_owner_account",
        side_effect=gh_cmd.RateLimitException("slow"),
    ):
        with pytest.raises(RateLimitException):
            gh_cmd.task_fetch_github_activity(dry_run=False)


@pytest.mark.django_db
def test_handle_core_invalid_range_resets_dates(caplog):
    caplog.set_level("WARNING")
    cmd = gh_cmd.Command()
    start = datetime(2025, 1, 2, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with patch.object(
        gh_cmd, "parse_iso_datetime", side_effect=[start, end]
    ), patch.object(
        gh_cmd,
        "task_fetch_github_activity",
        return_value=[],
    ) as fetch_mock, patch.object(
        gh_cmd, "_generate_markdown_for_synced", return_value={}
    ), patch.object(
        gh_cmd, "_push_markdown_to_github"
    ), override_settings(
        BOOST_LIBRARY_TRACKER_REPO_OWNER="",
        BOOST_LIBRARY_TRACKER_REPO_NAME="",
    ):
        cmd._handle_core(
            {
                "dry_run": False,
                "skip_github_sync": False,
                "skip_markdown_export": True,
                "skip_remote_push": True,
                "skip_pinecone": True,
                "since": "x",
                "until": "y",
                "from_repo": None,
            }
        )
    assert fetch_mock.called
    args, kwargs = fetch_mock.call_args
    assert kwargs.get("start_date") is None and kwargs.get("end_date") is None


@pytest.mark.django_db
def test_handle_core_skip_sync_skip_md_branch(caplog):
    caplog.set_level("INFO")
    cmd = gh_cmd.Command()
    with patch.object(gh_cmd, "_push_markdown_to_github"), override_settings(
        BOOST_LIBRARY_TRACKER_REPO_OWNER="",
        BOOST_LIBRARY_TRACKER_REPO_NAME="",
    ):
        cmd._handle_core(
            {
                "dry_run": False,
                "skip_github_sync": True,
                "skip_markdown_export": False,
                "skip_remote_push": False,
                "skip_pinecone": True,
                "since": None,
                "until": None,
                "from_repo": None,
            }
        )


@pytest.mark.django_db
def test_call_command_dry_run_skip_sync():
    with patch.object(gh_cmd, "task_fetch_github_activity") as fetch:
        call_command(
            "run_boost_github_activity_tracker",
            "--dry-run",
            "--skip-github-sync",
            stdout=MagicMock(),
            stderr=MagicMock(),
        )
    fetch.assert_not_called()


@pytest.mark.django_db
def test_handle_core_sync_writes_markdown(tmp_path):
    cmd = gh_cmd.Command()
    synced = [
        (
            "boostorg",
            "boost",
            MagicMock(),
            {"issues": [1], "pull_requests": [2]},
        )
    ]
    with patch.object(
        gh_cmd, "task_fetch_github_activity", return_value=synced
    ), patch.object(gh_cmd, "get_md_export_dir", return_value=tmp_path), patch.object(
        gh_cmd, "_generate_markdown_for_synced", return_value={"f.md": str(tmp_path)}
    ), patch.object(
        gh_cmd, "_push_markdown_to_github"
    ):
        cmd._handle_core(
            {
                "dry_run": False,
                "skip_github_sync": False,
                "skip_markdown_export": False,
                "skip_remote_push": True,
                "skip_pinecone": True,
                "since": None,
                "until": None,
                "from_repo": None,
            }
        )


@pytest.mark.django_db
def test_task_fetch_github_activity_non_dry_single_repo(github_account):
    github_account.username = "boostorg"
    github_account.save()
    mock_client = MagicMock()
    mock_client.get_file_content.return_value = (b"", "utf-8")
    gh_repo = MagicMock()
    boost_repo = MagicMock()
    sync_result = {"issues": [], "pull_requests": []}
    with patch.object(
        gh_cmd, "get_github_client", return_value=mock_client
    ), patch.object(
        gh_cmd, "get_or_create_owner_account", return_value=github_account
    ), patch.object(
        gh_cmd, "get_or_create_repository", return_value=(gh_repo, False)
    ), patch.object(
        gh_cmd, "ensure_repository_owner"
    ), patch.object(
        gh_cmd, "get_or_create_boost_library_repo", return_value=(boost_repo, False)
    ), patch.object(
        gh_cmd, "sync_github", return_value=sync_result
    ):
        synced = gh_cmd.task_fetch_github_activity(dry_run=False)
    assert len(synced) == 1
    assert synced[0][0] == "boostorg" and synced[0][1] == "boost"


@pytest.mark.django_db
def test_task_pinecone_sync_non_dry_invokes_issue_and_pr_paths():
    with patch.object(gh_cmd, "_run_pinecone_sync") as sync_mock:
        gh_cmd.task_pinecone_sync(dry_run=False)
    assert sync_mock.call_count == 2
