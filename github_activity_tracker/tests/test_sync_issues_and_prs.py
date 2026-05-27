"""Tests for sync_issues_and_prs unified sync function."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from github_activity_tracker.sync import issues_and_prs as issues_mod
from github_activity_tracker.sync.issues_and_prs import (
    sync_issues_and_prs,
)


@patch("github_activity_tracker.sync.issues_and_prs.PullRequest.objects")
@patch("github_activity_tracker.sync.issues_and_prs.Issue.objects")
@patch("github_activity_tracker.sync.issues_and_prs.get_github_client")
@patch("github_activity_tracker.sync.issues_and_prs.fetcher")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_issue_jsons")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_pr_jsons")
def test_sync_issues_and_prs_processes_both_types(
    mock_existing_prs,
    mock_existing_issues,
    mock_fetcher,
    mock_get_client,
    mock_issue_objects,
    mock_pr_objects,
):
    """sync_issues_and_prs routes items by key to issue or PR processing."""
    mock_repo = MagicMock()
    mock_repo.owner_account.username = "owner"
    mock_repo.repo_name = "repo"
    mock_issue_objects.filter.return_value.order_by.return_value.first.return_value = (
        None
    )
    mock_pr_objects.filter.return_value.order_by.return_value.first.return_value = None

    mock_existing_issues.return_value = (0, [])
    mock_existing_prs.return_value = (0, [])

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Yield one issue and one PR
    mock_fetcher.fetch_issues_and_prs_from_github.return_value = [
        {"issue_info": {"number": 1}, "comments": []},
        {"pr_info": {"number": 2}, "comments": [], "reviews": []},
    ]

    with (
        patch(
            "github_activity_tracker.sync.issues_and_prs._process_issue_data"
        ) as mock_proc_issue,
        patch(
            "github_activity_tracker.sync.issues_and_prs._process_pr_data"
        ) as mock_proc_pr,
        patch("github_activity_tracker.sync.issues_and_prs.save_issue_raw_source"),
        patch("github_activity_tracker.sync.issues_and_prs.save_pr_raw_source"),
        patch(
            "github_activity_tracker.sync.issues_and_prs.get_issue_json_path"
        ) as mock_issue_path,
        patch(
            "github_activity_tracker.sync.issues_and_prs.get_pr_json_path"
        ) as mock_pr_path,
    ):

        mock_issue_path.return_value = MagicMock()
        mock_pr_path.return_value = MagicMock()

        result = sync_issues_and_prs(mock_repo)

    assert result == {"issues": [1], "pull_requests": [2]}
    mock_proc_issue.assert_called_once()
    mock_proc_pr.assert_called_once()


@patch("github_activity_tracker.sync.issues_and_prs.PullRequest.objects")
@patch("github_activity_tracker.sync.issues_and_prs.Issue.objects")
@patch("github_activity_tracker.sync.issues_and_prs.get_github_client")
@patch("github_activity_tracker.sync.issues_and_prs.fetcher")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_issue_jsons")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_pr_jsons")
def test_sync_issues_and_prs_uses_max_start_date(
    mock_existing_prs,
    mock_existing_issues,
    mock_fetcher,
    mock_get_client,
    mock_issue_objects,
    mock_pr_objects,
):
    """sync_issues_and_prs uses the later of last_issue and last_pr (+1s) as start_date."""
    mock_repo = MagicMock()
    mock_repo.owner_account.username = "owner"
    mock_repo.repo_name = "repo"

    # Last issue updated at 2024-01-05
    mock_last_issue = MagicMock()
    mock_last_issue.issue_updated_at = datetime(2024, 1, 5, tzinfo=timezone.utc)
    mock_issue_objects.filter.return_value.order_by.return_value.first.return_value = (
        mock_last_issue
    )

    # Last PR updated at 2024-01-03 (older than last issue)
    mock_last_pr = MagicMock()
    mock_last_pr.pr_updated_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    mock_pr_objects.filter.return_value.order_by.return_value.first.return_value = (
        mock_last_pr
    )

    mock_existing_issues.return_value = (0, [])
    mock_existing_prs.return_value = (0, [])

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_fetcher.fetch_issues_and_prs_from_github.return_value = []

    sync_issues_and_prs(mock_repo)

    # Should use max(issue_date, pr_date) → 2024-01-05 + 1s
    call_args = mock_fetcher.fetch_issues_and_prs_from_github.call_args
    start_date = call_args[0][3]  # Fourth positional arg
    assert start_date == datetime(2024, 1, 5, 0, 0, 1, tzinfo=timezone.utc)


@patch("github_activity_tracker.sync.issues_and_prs.PullRequest.objects")
@patch("github_activity_tracker.sync.issues_and_prs.Issue.objects")
@patch("github_activity_tracker.sync.issues_and_prs.get_github_client")
@patch("github_activity_tracker.sync.issues_and_prs.fetcher")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_issue_jsons")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_pr_jsons")
def test_sync_issues_and_prs_processes_existing_jsons_first(
    mock_existing_prs,
    mock_existing_issues,
    mock_fetcher,
    mock_get_client,
    mock_issue_objects,
    mock_pr_objects,
):
    """sync_issues_and_prs processes leftover JSON files before fetching from GitHub."""
    mock_repo = MagicMock()
    mock_repo.owner_account.username = "owner"
    mock_repo.repo_name = "repo"
    mock_issue_objects.filter.return_value.order_by.return_value.first.return_value = (
        None
    )
    mock_pr_objects.filter.return_value.order_by.return_value.first.return_value = None

    # Existing JSONs found
    mock_existing_issues.return_value = (2, [10, 11])
    mock_existing_prs.return_value = (1, [20])

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_fetcher.fetch_issues_and_prs_from_github.return_value = []

    result = sync_issues_and_prs(mock_repo)

    # Should include existing numbers in result
    assert 10 in result["issues"]
    assert 11 in result["issues"]
    assert 20 in result["pull_requests"]
    mock_existing_issues.assert_called_once_with(mock_repo)
    mock_existing_prs.assert_called_once_with(mock_repo)


@patch("github_activity_tracker.sync.issues_and_prs.PullRequest.objects")
@patch("github_activity_tracker.sync.issues_and_prs.Issue.objects")
@patch("github_activity_tracker.sync.issues_and_prs.get_github_client")
@patch("github_activity_tracker.sync.issues_and_prs.fetcher")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_issue_jsons")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_pr_jsons")
def test_sync_issues_and_prs_respects_override_start_date(
    mock_existing_prs,
    mock_existing_issues,
    mock_fetcher,
    mock_get_client,
    mock_issue_objects,
    mock_pr_objects,
):
    """sync_issues_and_prs uses provided start_date instead of deriving from DB."""
    mock_repo = MagicMock()
    mock_repo.owner_account.username = "owner"
    mock_repo.repo_name = "repo"

    mock_existing_issues.return_value = (0, [])
    mock_existing_prs.return_value = (0, [])

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_fetcher.fetch_issues_and_prs_from_github.return_value = []

    override_start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    sync_issues_and_prs(mock_repo, start_date=override_start)

    # Should NOT query DB for last issue/PR
    mock_issue_objects.filter.assert_not_called()
    mock_pr_objects.filter.assert_not_called()

    # Should pass override_start to fetcher
    call_args = mock_fetcher.fetch_issues_and_prs_from_github.call_args
    assert call_args[0][3] == override_start


@patch("github_activity_tracker.sync.issues_and_prs.PullRequest.objects")
@patch("github_activity_tracker.sync.issues_and_prs.Issue.objects")
@patch("github_activity_tracker.sync.issues_and_prs.get_github_client")
@patch("github_activity_tracker.sync.issues_and_prs.fetcher")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_issue_jsons")
@patch("github_activity_tracker.sync.issues_and_prs._process_existing_pr_jsons")
def test_sync_issues_and_prs_saves_and_removes_json_files(
    mock_existing_prs,
    mock_existing_issues,
    mock_fetcher,
    mock_get_client,
    mock_issue_objects,
    mock_pr_objects,
):
    """sync_issues_and_prs writes JSON, processes, then removes file for each item."""
    mock_repo = MagicMock()
    mock_repo.owner_account.username = "owner"
    mock_repo.repo_name = "repo"
    mock_issue_objects.filter.return_value.order_by.return_value.first.return_value = (
        None
    )
    mock_pr_objects.filter.return_value.order_by.return_value.first.return_value = None

    mock_existing_issues.return_value = (0, [])
    mock_existing_prs.return_value = (0, [])

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_fetcher.fetch_issues_and_prs_from_github.return_value = [
        {"issue_info": {"number": 1}, "comments": []},
    ]

    mock_json_path = MagicMock()

    with (
        patch("github_activity_tracker.sync.issues_and_prs._process_issue_data"),
        patch("github_activity_tracker.sync.issues_and_prs.save_issue_raw_source"),
        patch(
            "github_activity_tracker.sync.issues_and_prs.get_issue_json_path",
            return_value=mock_json_path,
        ),
    ):

        sync_issues_and_prs(mock_repo)

    # Should write, then unlink
    mock_json_path.parent.mkdir.assert_called_once()
    mock_json_path.write_text.assert_called_once()
    mock_json_path.unlink.assert_called_once()


@pytest.mark.django_db
def test_process_issue_data_skips_without_user(github_repository):
    issue = {"number": 1, "user": None}
    issues_mod._process_issue_data(github_repository, issue)


@pytest.mark.django_db
def test_process_pr_data_skips_without_user(github_repository):
    pr = {"pr_info": {"number": 2, "user": None}}
    issues_mod._process_pr_data(github_repository, pr)


@pytest.mark.django_db
def test_process_existing_issue_jsons_bad_file(github_repository, tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{", encoding="utf-8")
    with patch.object(
        issues_mod,
        "iter_existing_issue_jsons",
        lambda owner, repo: [p],
    ):
        n, nums = issues_mod._process_existing_issue_jsons(github_repository)
    assert n == 0 and nums == []


@pytest.mark.django_db
def test_process_existing_pr_jsons_bad_file(github_repository, tmp_path):
    p = tmp_path / "p.json"
    p.write_text("{", encoding="utf-8")
    with patch.object(
        issues_mod,
        "iter_existing_pr_jsons",
        lambda owner, repo: [p],
    ):
        n, nums = issues_mod._process_existing_pr_jsons(github_repository)
    assert n == 0 and nums == []


@pytest.mark.django_db
def test_sync_issues_and_prs_issue_branch_none_number_raises(github_repository):
    from github_activity_tracker.api_schemas import GitHubApiValidationError

    item = {"issue_info": {"number": None}, "comments": []}

    with (
        patch.object(issues_mod, "_process_existing_issue_jsons", return_value=(0, [])),
        patch.object(issues_mod, "_process_existing_pr_jsons", return_value=(0, [])),
        patch.object(issues_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            issues_mod.fetcher,
            "fetch_issues_and_prs_from_github",
            lambda *a, **k: [item],
        ),
        patch.object(issues_mod, "RedisListETagCache", return_value=MagicMock()),
        pytest.raises(GitHubApiValidationError),
    ):
        issues_mod.sync_issues_and_prs(github_repository)


@pytest.mark.django_db
def test_sync_issues_and_prs_unexpected_error_wraps(github_repository):
    with (
        patch.object(issues_mod, "_process_existing_issue_jsons", return_value=(0, [])),
        patch.object(issues_mod, "_process_existing_pr_jsons", return_value=(0, [])),
        patch.object(issues_mod, "get_github_client", side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            issues_mod.sync_issues_and_prs(github_repository)


@pytest.mark.django_db
def test_sync_issues_start_date_issue_only_branch(github_repository):
    """When only last_issue exists, start_date is issue_date + 1s."""
    from github_activity_tracker.models import Issue

    Issue.objects.create(
        repo=github_repository,
        account=github_repository.owner_account,
        issue_id=900002,
        issue_number=2,
        title="t",
        body="",
        state="open",
        state_reason="",
        issue_created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        issue_updated_at=datetime(2024, 4, 10, tzinfo=timezone.utc),
    )

    mock_fetch = MagicMock(return_value=[])

    with (
        patch.object(issues_mod, "_process_existing_issue_jsons", return_value=(0, [])),
        patch.object(issues_mod, "_process_existing_pr_jsons", return_value=(0, [])),
        patch.object(issues_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            issues_mod.fetcher,
            "fetch_issues_and_prs_from_github",
            mock_fetch,
        ),
        patch.object(issues_mod, "RedisListETagCache", return_value=MagicMock()),
    ):
        issues_mod.sync_issues_and_prs(github_repository)

    start = mock_fetch.call_args[0][3]
    assert start == datetime(2024, 4, 10, 0, 0, 1, tzinfo=timezone.utc)


@pytest.mark.django_db
def test_sync_issues_start_date_pr_only_branch(github_repository):
    from github_activity_tracker.models import PullRequest

    PullRequest.objects.create(
        repo=github_repository,
        account=github_repository.owner_account,
        pr_id=800001,
        pr_number=3,
        title="p",
        body="",
        state="open",
        head_hash="",
        base_hash="",
        pr_created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        pr_updated_at=datetime(2024, 5, 5, tzinfo=timezone.utc),
    )

    mock_fetch = MagicMock(return_value=[])

    with (
        patch.object(issues_mod, "_process_existing_issue_jsons", return_value=(0, [])),
        patch.object(issues_mod, "_process_existing_pr_jsons", return_value=(0, [])),
        patch.object(issues_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            issues_mod.fetcher,
            "fetch_issues_and_prs_from_github",
            mock_fetch,
        ),
        patch.object(issues_mod, "RedisListETagCache", return_value=MagicMock()),
    ):
        issues_mod.sync_issues_and_prs(github_repository)

    start = mock_fetch.call_args[0][3]
    assert start == datetime(2024, 5, 5, 0, 0, 1, tzinfo=timezone.utc)


@pytest.mark.django_db
def test_process_issue_data_assignees_labels_and_comments(
    github_repository, make_github_account
):
    owner_acc = github_repository.owner_account
    other = make_github_account(
        github_account_id=888001,
        username="assignee-user",
    )
    data = {
        "number": 601,
        "id": 9000601,
        "title": "Issue T",
        "body": "body",
        "state": "open",
        "state_reason": "",
        "user": {
            "id": owner_acc.github_account_id,
            "login": owner_acc.username,
            "name": "",
            "avatar_url": "",
        },
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "closed_at": None,
        "comments": [
            {
                "id": 77001,
                "body": "c1",
                "user": {
                    "id": other.github_account_id,
                    "login": other.username,
                    "name": "",
                    "avatar_url": "",
                },
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": 77002,
                "body": "no user",
                "user": None,
            },
        ],
        "assignees": [
            {
                "id": owner_acc.github_account_id,
                "login": owner_acc.username,
                "name": "",
                "avatar_url": "",
            },
            {
                "id": other.github_account_id,
                "login": other.username,
                "name": "",
                "avatar_url": "",
            },
        ],
        "labels": [{"name": "bug"}, {"name": "docs"}],
    }
    issues_mod._process_issue_data(github_repository, data)
    issue = github_repository.issues.get(issue_number=601)
    assert issue.comments.count() == 1
    assert issue.assignees.count() == 2
    assert {il.label_name for il in issue.labels.all()} == {"bug", "docs"}

    data2 = {
        **data,
        "comments": [
            {
                "id": 77001,
                "body": "updated",
                "user": {
                    "id": other.github_account_id,
                    "login": other.username,
                    "name": "",
                    "avatar_url": "",
                },
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-03T00:00:00Z",
            }
        ],
        "assignees": [data["assignees"][0]],
        "labels": [{"name": "bug"}],
    }
    issues_mod._process_issue_data(github_repository, data2)
    issue.refresh_from_db()
    assert issue.comments.get(issue_comment_id=77001).body == "updated"
    assert issue.assignees.count() == 1
    assert {il.label_name for il in issue.labels.all()} == {"bug"}


@pytest.mark.django_db
def test_process_pr_data_reviews_comments_labels(
    github_repository, make_github_account
):
    owner_acc = github_repository.owner_account
    reviewer = make_github_account(github_account_id=888002, username="rev")
    pr_payload = {
        "number": 701,
        "id": 8000701,
        "title": "PR",
        "body": "",
        "state": "open",
        "user": {
            "id": owner_acc.github_account_id,
            "login": owner_acc.username,
            "name": "",
            "avatar_url": "",
        },
        "head": {"sha": "abc"},
        "base": {"sha": "def"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "merged_at": None,
        "closed_at": None,
        "comments": [
            {
                "id": 88001,
                "body": "pc",
                "user": {
                    "id": reviewer.github_account_id,
                    "login": reviewer.username,
                    "name": "",
                    "avatar_url": "",
                },
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ],
        "reviews": [
            {
                "id": 99001,
                "body": "lgtm",
                "in_reply_to_id": None,
                "user": {
                    "id": reviewer.github_account_id,
                    "login": reviewer.username,
                    "name": "",
                    "avatar_url": "",
                },
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": 99002,
                "body": "skip",
                "user": None,
            },
        ],
        "assignees": [
            {
                "id": owner_acc.github_account_id,
                "login": owner_acc.username,
                "name": "",
                "avatar_url": "",
            },
            {
                "id": reviewer.github_account_id,
                "login": reviewer.username,
                "name": "",
                "avatar_url": "",
            },
        ],
        "labels": [{"name": "pr-label"}],
    }
    issues_mod._process_pr_data(github_repository, pr_payload)
    pr = github_repository.pull_requests.get(pr_number=701)
    assert pr.comments.count() == 1
    assert pr.reviews.count() == 1
    assert pr.assignees.count() == 2

    pr_payload2 = {
        **pr_payload,
        "assignees": [pr_payload["assignees"][0]],
        "labels": [],
    }
    issues_mod._process_pr_data(github_repository, pr_payload2)
    pr.refresh_from_db()
    assert pr.assignees.count() == 1
    assert list(pr.labels.all()) == []


@pytest.mark.django_db
def test_sync_issues_and_prs_rate_limit(github_repository):
    from core.operations.github_ops.client import RateLimitException

    with (
        patch.object(issues_mod, "_process_existing_issue_jsons", return_value=(0, [])),
        patch.object(issues_mod, "_process_existing_pr_jsons", return_value=(0, [])),
        patch.object(
            issues_mod, "get_github_client", side_effect=RateLimitException("rl")
        ),
    ):
        with pytest.raises(RateLimitException):
            issues_mod.sync_issues_and_prs(github_repository)


@pytest.mark.django_db
def test_process_existing_issue_jsons_success_nested(
    github_repository,
    tmp_path,
):
    owner_acc = github_repository.owner_account
    body = {
        "issue_info": {
            "number": 602,
            "id": 9000602,
            "title": "nested",
            "body": "",
            "state": "open",
            "state_reason": "",
            "user": {
                "id": owner_acc.github_account_id,
                "login": owner_acc.username,
                "name": "",
                "avatar_url": "",
            },
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "closed_at": None,
            "comments": [],
            "assignees": [],
            "labels": [],
        },
        "comments": [],
    }
    p = tmp_path / "602.json"
    p.write_text(json.dumps(body), encoding="utf-8")
    with (
        patch.object(
            issues_mod,
            "iter_existing_issue_jsons",
            lambda owner, repo: [p],
        ),
        patch.object(issues_mod, "save_issue_raw_source"),
    ):
        n, nums = issues_mod._process_existing_issue_jsons(github_repository)
    assert n == 1 and nums == [602]
    assert not p.exists()


@pytest.mark.django_db
def test_sync_issues_pr_info_present_but_number_none_raises(github_repository):
    from github_activity_tracker.api_schemas import GitHubApiValidationError

    item = {"pr_info": {}, "comments": []}
    with (
        patch.object(issues_mod, "_process_existing_issue_jsons", return_value=(0, [])),
        patch.object(issues_mod, "_process_existing_pr_jsons", return_value=(0, [])),
        patch.object(issues_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            issues_mod.fetcher,
            "fetch_issues_and_prs_from_github",
            lambda *a, **k: [item],
        ),
        patch.object(issues_mod, "RedisListETagCache", return_value=MagicMock()),
        pytest.raises(GitHubApiValidationError),
    ):
        issues_mod.sync_issues_and_prs(github_repository)


@pytest.mark.django_db
def test_process_existing_pr_jsons_success_nested(github_repository, tmp_path):
    owner_acc = github_repository.owner_account
    body = {
        "pr_info": {
            "number": 703,
            "id": 8000703,
            "title": "pr nested",
            "body": "",
            "state": "open",
            "user": {
                "id": owner_acc.github_account_id,
                "login": owner_acc.username,
                "name": "",
                "avatar_url": "",
            },
            "head": {"sha": "a"},
            "base": {"sha": "b"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "merged_at": None,
            "closed_at": None,
            "comments": [],
            "reviews": [],
            "assignees": [],
            "labels": [],
        },
        "comments": [],
        "reviews": [],
    }
    p = tmp_path / "703.json"
    p.write_text(json.dumps(body), encoding="utf-8")
    with (
        patch.object(
            issues_mod,
            "iter_existing_pr_jsons",
            lambda owner, repo: [p],
        ),
        patch.object(issues_mod, "save_pr_raw_source"),
    ):
        n, nums = issues_mod._process_existing_pr_jsons(github_repository)
    assert n == 1 and nums == [703]
    assert not p.exists()
