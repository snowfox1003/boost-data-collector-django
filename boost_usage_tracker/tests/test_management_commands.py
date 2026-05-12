"""Tests for boost_usage_tracker management commands."""

import logging
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import CommandError, call_command

from boost_usage_tracker.management.commands import (
    run_update_created_repos_by_language as ruc,
)
from boost_usage_tracker.management.commands import run_update_db as rud
from boost_usage_tracker.management.commands.run_boost_usage_tracker import (
    BoostUsageTrackerCollector,
    Command as UsageCommand,
    _ensure_github_repo,
    _run_boost_search_stage,
    task_monitor_content,
    task_monitor_stars,
)
from boost_usage_tracker.repo_searcher import RepoSearchResult
from core.operations.github_ops.client import ConnectionException, RateLimitException


def _ok_created_repos_result(**kwargs):
    base = {
        "languages_requested": ["C++"],
        "languages_processed": ["C++"],
        "languages_missing": [],
        "start_year": 2010,
        "end_year": 2020,
        "stars_min": 10,
        "created": 0,
        "updated": 0,
        "rows_processed": 0,
        "errors": [],
    }
    base.update(kwargs)
    return base


@pytest.mark.django_db
def test_run_update_db_github_account_success():
    result = {
        "errors": [],
        "table": "github_account",
        "source_path": "/workspace/x",
        "created": 1,
        "updated": 2,
    }
    out = StringIO()

    def runner(source):
        return result

    gh_entry = (
        runner,
        rud._format_github_account,
        rud.TARGETS["github_account"][2],
    )
    with patch.dict(rud.TARGETS, {"github_account": gh_entry}, clear=False):
        call_command("run_update_db", "--target=github_account", stdout=out)
    assert "created=1" in out.getvalue()


@pytest.mark.django_db
def test_run_update_db_raises_on_errors():
    def bad_runner(source):
        return {"errors": ["row bad"]}

    repo_entry = (
        bad_runner,
        rud._format_repository,
        rud.TARGETS["repository"][2],
    )
    with patch.dict(rud.TARGETS, {"repository": repo_entry}, clear=False):
        with pytest.raises(CommandError, match="failed"):
            call_command(
                "run_update_db",
                "--target=repository",
                stdout=StringIO(),
                stderr=StringIO(),
            )


@pytest.mark.django_db
def test_run_update_created_repos_success_stdout():
    out = StringIO()
    err = StringIO()
    fake = _ok_created_repos_result()
    cmd = ruc.Command(stdout=out, stderr=err)
    with patch(
        "boost_usage_tracker.management.commands.run_update_created_repos_by_language.update_created_repos_by_language",
        return_value=fake,
    ):
        ret = cmd.handle(
            languages=None,
            start_year=2010,
            end_year=None,
            stars_min=10,
            sleep_seconds=0.0,
            fail_on_missing_language=False,
        )
    assert ret == 0
    assert "languages_requested=1" in out.getvalue()


@pytest.mark.django_db
def test_run_update_created_repos_errors_stderr_and_exit_code():
    out = StringIO()
    err = StringIO()
    fake = _ok_created_repos_result(errors=["language missing"])
    cmd = ruc.Command(stdout=out, stderr=err)
    with patch(
        "boost_usage_tracker.management.commands.run_update_created_repos_by_language.update_created_repos_by_language",
        return_value=fake,
    ):
        ret = cmd.handle(
            languages=None,
            start_year=2010,
            end_year=None,
            stars_min=10,
            sleep_seconds=0.0,
            fail_on_missing_language=False,
        )
    assert ret == 1
    assert "language missing" in err.getvalue()


def test_run_boost_usage_dry_run_invokes_tasks():
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.task_monitor_content",
        ) as t1,
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.task_monitor_stars",
        ) as t2,
    ):
        call_command("run_boost_usage_tracker", "--dry-run", stdout=StringIO())
    t1.assert_called_once()
    t2.assert_called_once()


def test_run_boost_usage_tracker_command_error_when_scraping_token_invalid():
    with patch(
        "boost_usage_tracker.management.commands.run_boost_usage_tracker.validate_github_token_for_use",
        side_effect=ValueError("GitHub scraping token is invalid"),
    ):
        with pytest.raises(CommandError, match="GitHub scraping token is invalid"):
            call_command("run_boost_usage_tracker", "--dry-run", stdout=StringIO())


def test_run_boost_usage_task_filter_monitor_content_only():
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.task_monitor_content",
        ) as t1,
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.task_monitor_stars",
        ) as t2,
    ):
        call_command(
            "run_boost_usage_tracker",
            "--task=monitor_content",
            "--dry-run",
            stdout=StringIO(),
        )
    t1.assert_called_once()
    t2.assert_not_called()


def test_usage_collector_get_collector_invalid_since_falls_back():
    cmd = UsageCommand()
    collector = cmd.get_collector(
        task=None,
        dry_run=True,
        min_stars=10,
        since="not-a-date",
        until=None,
    )
    assert isinstance(collector, BoostUsageTrackerCollector)
    assert collector.since <= collector.until


@pytest.mark.django_db
def test_ensure_github_repo_creates_repo(github_account, github_repository):
    client = MagicMock()
    result = RepoSearchResult(full_name="acme/demo", stars=3)
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.get_or_create_owner_account",
            return_value=github_account,
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.get_or_create_repository",
            return_value=(github_repository, False),
        ),
    ):
        repo = _ensure_github_repo(client, result)
    assert repo is github_repository


def test_run_boost_search_stage_empty_inputs():
    client = MagicMock()
    totals = _run_boost_search_stage(
        client,
        [],
        last_commit_dt=datetime.now(timezone.utc),
    )
    assert totals["processed"] == 0


def test_run_boost_search_stage_batch_search_raises():
    client = MagicMock()
    repos = [RepoSearchResult(full_name="a/r", stars=5)]
    with patch(
        "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_boost_include_files_batch",
        side_effect=ConnectionException("down"),
    ):
        with pytest.raises(ConnectionException):
            _run_boost_search_stage(
                client,
                repos,
                last_commit_dt=datetime.now(timezone.utc),
            )


def test_task_monitor_content_non_dry_run_processes_repo():
    repos = [RepoSearchResult(full_name="own/repo", stars=15)]
    since = datetime(2024, 6, 1, tzinfo=timezone.utc)
    until = datetime(2024, 6, 2, tzinfo=timezone.utc)
    mock_client = MagicMock()
    stats = {
        "boost_used": 0,
        "usages_created": 0,
        "usages_updated": 0,
        "usages_excepted": 0,
        "missing_header_recorded": 0,
    }
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_repos_with_date_splitting",
            return_value=repos,
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_boost_include_files_batch",
            return_value=[],
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.process_single_repo",
            return_value=stats,
        ),
    ):
        task_monitor_content(since, until, min_stars=10, dry_run=False)


@pytest.mark.django_db
def test_task_monitor_stars_dry_run_no_results():
    mock_client = MagicMock()
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_repos_with_date_splitting",
            return_value=[],
        ),
    ):
        task_monitor_stars(min_stars=10, dry_run=True)


@pytest.mark.django_db
def test_run_update_db_githubfile_target_success():
    result = {
        "errors": [],
        "source_path": "/f.csv",
        "created": 0,
        "updated": 1,
        "skipped_no_repo": 0,
    }
    out = StringIO()

    def runner(source):
        return result

    entry = (runner, rud._format_githubfile, rud.TARGETS["githubfile"][2])
    with patch.dict(rud.TARGETS, {"githubfile": entry}, clear=False):
        call_command("run_update_db", "--target=githubfile", stdout=out)
    assert "skipped_no_repo=0" in out.getvalue()


@pytest.mark.django_db
def test_run_update_created_repos_cli_passes_year_range():
    out = StringIO()
    fake = _ok_created_repos_result(start_year=2011, end_year=2012)
    with patch(
        "boost_usage_tracker.management.commands.run_update_created_repos_by_language.update_created_repos_by_language",
        return_value=fake,
    ):
        call_command(
            "run_update_created_repos_by_language",
            "--start-year=2011",
            "--end-year=2012",
            stdout=out,
        )
    body = out.getvalue()
    assert "2011" in body and "2012" in body


@pytest.mark.django_db
def test_task_monitor_stars_non_dry_empty_search():
    mock_client = MagicMock()
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_repos_with_date_splitting",
            return_value=[],
        ),
    ):
        task_monitor_stars(min_stars=10, dry_run=False)


@pytest.mark.django_db
def test_run_update_db_repository_target_success():
    result = {
        "errors": [],
        "source_path": "/r.csv",
        "created_repos": 0,
        "updated_repos": 1,
        "created_ext": 0,
        "updated_ext": 0,
        "skipped_no_owner": 0,
    }

    def runner(source):
        return result

    entry = (runner, rud._format_repository, rud.TARGETS["repository"][2])
    with patch.dict(rud.TARGETS, {"repository": entry}, clear=False):
        out = StringIO()
        call_command("run_update_db", "--target=repository", stdout=out)
    assert "repos:" in out.getvalue()


@pytest.mark.django_db
def test_run_update_db_boostusage_target_success():
    result = {
        "errors": [],
        "source_path": "/u.csv",
        "created": 1,
        "updated": 0,
        "skipped_no_repo": 0,
        "skipped_no_file": 0,
        "skipped_no_boost_header": 0,
    }

    def runner(source):
        return result

    entry = (runner, rud._format_boostusage, rud.TARGETS["boostusage"][2])
    with patch.dict(rud.TARGETS, {"boostusage": entry}, clear=False):
        out = StringIO()
        call_command("run_update_db", "--target=boostusage", stdout=out)
    assert "skipped_no_boost_header=0" in out.getvalue()


@pytest.mark.django_db
def test_run_update_db_github_account_invokes_module_runner():
    payload = {
        "errors": [],
        "table": "github_account",
        "source_path": "/workspace/x",
        "created": 0,
        "updated": 1,
    }
    out = StringIO()
    with patch(
        "boost_usage_tracker.update_git_account.update_git_account",
        return_value=payload,
    ):
        call_command("run_update_db", "--target=github_account", stdout=out)
    assert "updated=1" in out.getvalue()


@pytest.mark.django_db
def test_task_monitor_stars_bulk_updates_tracked_repo_stars(
    ext_repo, external_github_repository, github_account
):
    github_account.username = "bulkowner"
    github_account.save()
    external_github_repository.owner_account = github_account
    external_github_repository.repo_name = "bulkrepo"
    external_github_repository.stars = 5
    external_github_repository.save()

    found = RepoSearchResult(full_name="bulkowner/bulkrepo", stars=77)
    mock_client = MagicMock()
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_repos_with_date_splitting",
            return_value=[found],
        ),
    ):
        task_monitor_stars(min_stars=10, dry_run=False)
    ext_repo.refresh_from_db()
    assert ext_repo.stars == 77


@pytest.mark.django_db
def test_run_update_db_repository_import_runner_invoked():
    payload = {
        "errors": [],
        "source_path": "/path/repo.csv",
        "created_repos": 0,
        "updated_repos": 1,
        "created_ext": 0,
        "updated_ext": 0,
        "skipped_no_owner": 0,
    }
    out = StringIO()
    with patch(
        "boost_usage_tracker.update_repository_from_csv.update_repository_table_from_csv",
        return_value=payload,
    ):
        call_command("run_update_db", "--target=repository", stdout=out)
    assert "repos:" in out.getvalue() and "updated=1" in out.getvalue()


@pytest.mark.django_db
def test_run_update_db_githubfile_import_runner_invoked():
    payload = {
        "errors": [],
        "source_path": "/f.csv",
        "created": 2,
        "updated": 0,
        "skipped_no_repo": 0,
    }
    out = StringIO()
    with patch(
        "boost_usage_tracker.update_githubfile_from_csv.update_githubfile_table_from_csv",
        return_value=payload,
    ):
        call_command("run_update_db", "--target=githubfile", stdout=out)
    assert "created=2" in out.getvalue()


@pytest.mark.django_db
def test_run_update_db_boostusage_import_runner_invoked():
    payload = {
        "errors": [],
        "source_path": "/u.csv",
        "created": 0,
        "updated": 3,
        "skipped_no_repo": 0,
        "skipped_no_file": 0,
        "skipped_no_boost_header": 0,
    }
    out = StringIO()
    with patch(
        "boost_usage_tracker.update_boostusage_from_csv.update_boostusage_table_from_csv",
        return_value=payload,
    ):
        call_command("run_update_db", "--target=boostusage", stdout=out)
    assert "updated=3" in out.getvalue()


def test_boost_usage_collector_propagates_rate_limit():
    cmd = UsageCommand()
    collector = cmd.get_collector(
        task="monitor_content",
        dry_run=False,
        min_stars=10,
        since=None,
        until=None,
    )
    with patch(
        "boost_usage_tracker.management.commands.run_boost_usage_tracker.task_monitor_content",
        side_effect=RateLimitException("slow"),
    ):
        with pytest.raises(RateLimitException):
            collector.run()


def test_monitor_content_dry_run_truncates_long_repo_list(caplog):
    caplog.set_level(logging.INFO)
    repos = [RepoSearchResult(full_name=f"o/r{i}", stars=12) for i in range(22)]
    mock_client = MagicMock()
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)
    until = datetime(2024, 1, 2, tzinfo=timezone.utc)
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_repos_with_date_splitting",
            return_value=repos,
        ),
    ):
        task_monitor_content(since, until, min_stars=10, dry_run=True)
    assert any("more" in r.message.lower() for r in caplog.records)


def test_run_boost_search_stage_skips_repo_when_processing_errors(caplog):
    caplog.set_level(logging.WARNING)
    client = MagicMock()
    repos = [RepoSearchResult(full_name="bad/repo", stars=9)]
    with (
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.search_boost_include_files_batch",
            return_value=[],
        ),
        patch(
            "boost_usage_tracker.management.commands.run_boost_usage_tracker.process_single_repo",
            side_effect=RuntimeError("bad repo"),
        ),
    ):
        totals = _run_boost_search_stage(
            client,
            repos,
            last_commit_dt=datetime.now(timezone.utc),
        )
    assert totals["processed"] == 0
    assert any("Skipping" in r.message for r in caplog.records)
