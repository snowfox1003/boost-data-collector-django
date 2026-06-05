"""
Sync GitHub issues and pull requests together using a single /issues list API call.

Flow:
1. Process existing JSON files in workspace/<owner>/<repo>/issues/*.json and prs/*.json.
2. Fetch from GitHub via fetch_issues_and_prs_from_github (one endpoint, routes by key).
   For each item: save as JSON, persist to DB, remove file.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Union

from cppa_user_tracker.services import get_or_create_github_account
from github_activity_tracker import fetcher, services
from github_activity_tracker.api_schemas import (
    GitHubIssueBundle,
    GitHubPullRequestBundle,
    GitHubUser,
    parse_issue_bundle,
    parse_pr_bundle,
)
from github_activity_tracker.sync.etag_cache import RedisListETagCache
from github_activity_tracker.sync.raw_source import (
    save_issue_raw_source,
    save_pr_raw_source,
)
from github_activity_tracker.sync.utils import (
    parse_datetime,
    parse_github_user,
)
from github_activity_tracker.workspace import (
    get_issue_json_path,
    get_pr_json_path,
    iter_existing_issue_jsons,
    iter_existing_pr_jsons,
)
from core.operations.github_ops import get_github_client
from core.operations.github_ops.client import ConnectionException, RateLimitException

from github_activity_tracker.models import (
    GitHubRepository,
    Issue,
    IssueLabel,
    PullRequest,
    PullRequestLabel,
)

logger = logging.getLogger(__name__)


def _user_info_from_model(user: GitHubUser | None) -> dict:
    return parse_github_user(user.model_dump() if user is not None else None)


def _issue_bundle_to_storage_dict(bundle: GitHubIssueBundle) -> dict:
    detail = bundle.issue.model_dump()
    comments = detail.pop("comments", [])
    return {"issue_info": detail, "comments": comments}


def _pr_bundle_to_storage_dict(bundle: GitHubPullRequestBundle) -> dict:
    detail = bundle.pr.model_dump()
    comments = detail.pop("comments", [])
    reviews = detail.pop("reviews", [])
    return {"pr_info": detail, "comments": comments, "reviews": reviews}


def _process_issue_data(
    repo: GitHubRepository,
    issue_data: Union[GitHubIssueBundle, dict],
) -> None:
    """Apply one issue bundle to the database. Accepts validated bundle or raw dict."""
    if isinstance(issue_data, dict):
        issue_data = parse_issue_bundle(issue_data)
    issue = issue_data.issue
    user_info = _user_info_from_model(issue.user)
    if not user_info["account_id"]:
        logger.warning(
            "Issue #%s: no user account_id; skipping",
            issue.number if issue.number is not None else "?",
        )
        return
    account, _ = get_or_create_github_account(
        github_account_id=user_info["account_id"],
        username=user_info["username"],
        display_name=user_info["display_name"],
        avatar_url=user_info["avatar_url"],
    )

    if issue.number is None or issue.id is None:
        logger.warning(
            "Issue missing number or id; skipping (got number=%r id=%r)",
            issue.number,
            issue.id,
        )
        return
    try:
        issue_number = int(issue.number)
        issue_id = int(issue.id)
    except (TypeError, ValueError):
        logger.warning(
            "Issue number/id not numeric; skipping (got number=%r id=%r)",
            issue.number,
            issue.id,
        )
        return

    issue_obj, _ = services.create_or_update_issue(
        repo=repo,
        account=account,
        issue_number=issue_number,
        issue_id=issue_id,
        title=issue.title or "",
        body=issue.body or "",
        state=issue.state or "open",
        state_reason=issue.state_reason or "",
        issue_created_at=parse_datetime(issue.created_at),
        issue_updated_at=parse_datetime(issue.updated_at),
        issue_closed_at=parse_datetime(issue.closed_at),
    )

    for comment_data in issue.comments:
        if comment_data.id is None:
            continue
        comment_user_info = _user_info_from_model(comment_data.user)
        if comment_user_info["account_id"]:
            comment_account, _ = get_or_create_github_account(
                github_account_id=comment_user_info["account_id"],
                username=comment_user_info["username"],
                display_name=comment_user_info["display_name"],
                avatar_url=comment_user_info["avatar_url"],
            )
            services.create_or_update_issue_comment(
                issue=issue_obj,
                account=comment_account,
                issue_comment_id=comment_data.id,
                body=comment_data.body or "",
                issue_comment_created_at=parse_datetime(comment_data.created_at),
                issue_comment_updated_at=parse_datetime(comment_data.updated_at),
            )

    assignee_infos = [_user_info_from_model(a) for a in issue.assignees]
    current_assignee_ids = {i["account_id"] for i in assignee_infos if i["account_id"]}
    for assignee_account in issue_obj.assignees.all():
        if assignee_account.github_account_id not in current_assignee_ids:
            services.remove_issue_assignee(issue_obj, assignee_account)
    for assignee_info in assignee_infos:
        if assignee_info["account_id"]:
            assignee_account, _ = get_or_create_github_account(
                github_account_id=assignee_info["account_id"],
                username=assignee_info["username"],
                display_name=assignee_info["display_name"],
                avatar_url=assignee_info["avatar_url"],
            )
            services.add_issue_assignee(issue_obj, assignee_account)

    incoming_label_names = {
        (label.name or "") for label in issue.labels if (label.name or "")
    }
    existing_label_names = {
        il.label_name
        for il in IssueLabel.objects.filter(issue=issue_obj)
        if il.label_name
    }
    for label_name in existing_label_names - incoming_label_names:
        services.remove_issue_label(issue_obj, label_name)
    for label_name in incoming_label_names - existing_label_names:
        services.add_issue_label(issue_obj, label_name)

    logger.debug("Issue #%s: saved to DB", issue.number)


def _process_existing_issue_jsons(
    repo: GitHubRepository,
) -> tuple[int, list[int]]:
    """Load each issues/*.json in workspace for this repo, save to DB, remove file.

    Returns:
        (count, issue_numbers) — count of processed files and their issue numbers.
    """
    owner = repo.owner_account.username
    repo_name = repo.repo_name
    count = 0
    numbers: list[int] = []
    for path in iter_existing_issue_jsons(owner, repo_name):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            bundle = parse_issue_bundle(raw, source=str(path))
            _process_issue_data(repo, bundle)
            save_issue_raw_source(
                owner, repo_name, _issue_bundle_to_storage_dict(bundle)
            )
            path.unlink()
            number = bundle.issue.number
            if number is not None:
                numbers.append(number)
            count += 1
        except Exception as e:
            logger.exception("Failed to process %s: %s", path, e)
    return count, numbers


def _process_pr_data(
    repo: GitHubRepository,
    pr_data: Union[GitHubPullRequestBundle, dict],
) -> None:
    """Apply one PR bundle to the database. Accepts validated bundle or raw dict."""
    if isinstance(pr_data, dict):
        pr_data = parse_pr_bundle(pr_data)
    pr = pr_data.pr
    user_info = _user_info_from_model(pr.user)
    if not user_info["account_id"]:
        logger.warning(
            "PR #%s: no user account_id; skipping",
            pr.number if pr.number is not None else "?",
        )
        return
    account, _ = get_or_create_github_account(
        github_account_id=user_info["account_id"],
        username=user_info["username"],
        display_name=user_info["display_name"],
        avatar_url=user_info["avatar_url"],
    )

    if pr.number is None or pr.id is None:
        logger.warning(
            "PR missing number or id; skipping (got number=%r id=%r)",
            pr.number,
            pr.id,
        )
        return
    try:
        pr_number = int(pr.number)
        pr_id = int(pr.id)
    except (TypeError, ValueError):
        logger.warning(
            "PR number/id not numeric; skipping (got number=%r id=%r)",
            pr.number,
            pr.id,
        )
        return

    pr_obj, _ = services.create_or_update_pull_request(
        repo=repo,
        account=account,
        pr_number=pr_number,
        pr_id=pr_id,
        title=pr.title or "",
        body=pr.body or "",
        state=pr.state or "open",
        head_hash=(pr.head.sha if pr.head else "") or "",
        base_hash=(pr.base.sha if pr.base else "") or "",
        pr_created_at=parse_datetime(pr.created_at),
        pr_updated_at=parse_datetime(pr.updated_at),
        pr_merged_at=parse_datetime(pr.merged_at),
        pr_closed_at=parse_datetime(pr.closed_at),
    )

    for comment_data in pr.comments:
        if comment_data.id is None:
            continue
        comment_user_info = _user_info_from_model(comment_data.user)
        if comment_user_info["account_id"]:
            comment_account, _ = get_or_create_github_account(
                github_account_id=comment_user_info["account_id"],
                username=comment_user_info["username"],
                display_name=comment_user_info["display_name"],
                avatar_url=comment_user_info["avatar_url"],
            )
            services.create_or_update_pr_comment(
                pr=pr_obj,
                account=comment_account,
                pr_comment_id=comment_data.id,
                body=comment_data.body or "",
                pr_comment_created_at=parse_datetime(comment_data.created_at),
                pr_comment_updated_at=parse_datetime(comment_data.updated_at),
            )

    for review_data in pr.reviews:
        if review_data.id is None:
            continue
        review_user_info = _user_info_from_model(review_data.user)
        if review_user_info["account_id"]:
            review_account, _ = get_or_create_github_account(
                github_account_id=review_user_info["account_id"],
                username=review_user_info["username"],
                display_name=review_user_info["display_name"],
                avatar_url=review_user_info["avatar_url"],
            )
            services.create_or_update_pr_review(
                pr=pr_obj,
                account=review_account,
                pr_review_id=review_data.id,
                body=review_data.body or "",
                in_reply_to_id=review_data.in_reply_to_id,
                pr_review_created_at=parse_datetime(review_data.created_at),
                pr_review_updated_at=parse_datetime(review_data.updated_at),
            )

    assignee_infos = [_user_info_from_model(a) for a in pr.assignees]
    current_assignee_ids = {i["account_id"] for i in assignee_infos if i["account_id"]}
    for assignee_account in pr_obj.assignees.all():
        if assignee_account.github_account_id not in current_assignee_ids:
            services.remove_pr_assignee(pr_obj, assignee_account)
    for assignee_info in assignee_infos:
        if assignee_info["account_id"]:
            assignee_account, _ = get_or_create_github_account(
                github_account_id=assignee_info["account_id"],
                username=assignee_info["username"],
                display_name=assignee_info["display_name"],
                avatar_url=assignee_info["avatar_url"],
            )
            services.add_pr_assignee(pr_obj, assignee_account)

    incoming_pr_label_names = {
        (label.name or "") for label in pr.labels if (label.name or "")
    }
    existing_pr_label_names = {
        pl.label_name
        for pl in PullRequestLabel.objects.filter(pr=pr_obj)
        if pl.label_name
    }
    for label_name in existing_pr_label_names - incoming_pr_label_names:
        services.remove_pull_request_label(pr_obj, label_name)
    for label_name in incoming_pr_label_names - existing_pr_label_names:
        services.add_pull_request_label(pr_obj, label_name)

    logger.debug("PR #%s: saved to DB", pr.number)


def _process_existing_pr_jsons(
    repo: GitHubRepository,
) -> tuple[int, list[int]]:
    """Load each prs/*.json in workspace for this repo, save to DB, remove file.

    Returns:
        (count, pr_numbers) — count of processed files and their PR numbers.
    """
    owner = repo.owner_account.username
    repo_name = repo.repo_name
    count = 0
    numbers: list[int] = []
    for path in iter_existing_pr_jsons(owner, repo_name):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            bundle = parse_pr_bundle(raw, source=str(path))
            _process_pr_data(repo, bundle)
            save_pr_raw_source(owner, repo_name, _pr_bundle_to_storage_dict(bundle))
            path.unlink()
            number = bundle.pr.number
            if number is not None:
                numbers.append(number)
            count += 1
        except Exception as e:
            logger.exception("Failed to process %s: %s", path, e)
    return count, numbers


def sync_issues_and_prs(
    repo: GitHubRepository,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> dict[str, list[int]]:
    """Sync issues and PRs for a repo using a single GitHub /issues list call.

    1. Process any existing issue/PR JSON files left from a previous interrupted run.
    2. Determine the start date as the later (max) of the last-seen issue and PR update times.
    3. Fetch items via fetch_issues_and_prs_from_github; each item is routed by key:
       - "issue_info" → persisted as an issue
       - "pr_info"    → persisted as a pull request

    Args:
        repo: Repository to sync.
        start_date: Override start date (default: derived from DB; see below).
        end_date: Override end date (default: None = no upper bound).

    Returns:
        {"issues": [<numbers>], "pull_requests": [<numbers>]}
    """
    logger.info(
        "sync_issues_and_prs: starting for repo id=%s (%s)",
        repo.pk,
        repo.repo_name,
    )

    owner = repo.owner_account.username
    repo_name = repo.repo_name
    issue_numbers: list[int] = []
    pr_numbers: list[int] = []

    try:
        # Phase 1: process any JSON files left from a previous interrupted run.
        n_issues, existing_issue_nums = _process_existing_issue_jsons(repo)
        issue_numbers.extend(existing_issue_nums)
        n_prs, existing_pr_nums = _process_existing_pr_jsons(repo)
        pr_numbers.extend(existing_pr_nums)
        if n_issues or n_prs:
            logger.info(
                "sync_issues_and_prs: processed %s existing issue JSON(s), %s existing PR JSON(s)",
                n_issues,
                n_prs,
            )

        # Phase 2: determine start date as max(last issue, last PR) +1s — shared /issues timeline.
        if start_date is None:
            last_issue = (
                Issue.objects.filter(repo=repo).order_by("-issue_updated_at").first()
            )
            last_pr = (
                PullRequest.objects.filter(repo=repo).order_by("-pr_updated_at").first()
            )

            issue_date = (
                (last_issue.issue_updated_at + timedelta(seconds=1))
                if last_issue and last_issue.issue_updated_at is not None
                else None
            )
            pr_date = (
                (last_pr.pr_updated_at + timedelta(seconds=1))
                if last_pr and last_pr.pr_updated_at is not None
                else None
            )

            if issue_date and pr_date:
                start_date = max(issue_date, pr_date)
            else:
                start_date = issue_date or pr_date

        # Phase 3: fetch from GitHub, write JSON, persist to DB, remove file.
        client = get_github_client()
        if client is None:
            raise RuntimeError("GitHub client unavailable for sync_issues_and_prs")
        etag_cache = RedisListETagCache(repo_id=repo.pk)
        count_issues = 0
        count_prs = 0

        for item in fetcher.fetch_issues_and_prs_from_github(
            client,
            owner,
            repo_name,
            start_date,
            end_date,
            etag_cache=etag_cache,
        ):
            if isinstance(item, GitHubPullRequestBundle):
                pr_bundle = item
            elif isinstance(item, dict) and "pr_info" in item:
                pr_bundle = parse_pr_bundle(item)
            else:
                if isinstance(item, GitHubIssueBundle):
                    issue_bundle = item
                elif isinstance(item, dict):
                    issue_bundle = parse_issue_bundle(item)
                else:
                    continue
                issue_number = issue_bundle.issue.number
                if issue_number is None:
                    continue
                storage = _issue_bundle_to_storage_dict(issue_bundle)
                json_path = get_issue_json_path(owner, repo_name, issue_number)
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_path.write_text(
                    json.dumps(storage, indent=2, default=str), encoding="utf-8"
                )
                _process_issue_data(repo, issue_bundle)
                save_issue_raw_source(owner, repo_name, storage)
                json_path.unlink()
                issue_numbers.append(issue_number)
                count_issues += 1
                continue

            pr_number = pr_bundle.pr.number
            if pr_number is None:
                continue
            storage = _pr_bundle_to_storage_dict(pr_bundle)
            json_path = get_pr_json_path(owner, repo_name, pr_number)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                json.dumps(storage, indent=2, default=str), encoding="utf-8"
            )
            _process_pr_data(repo, pr_bundle)
            save_pr_raw_source(owner, repo_name, storage)
            json_path.unlink()
            pr_numbers.append(pr_number)
            count_prs += 1

        logger.info(
            "sync_issues_and_prs: finished for repo id=%s; "
            "%s existing issues + %s fetched; %s existing PRs + %s fetched",
            repo.pk,
            n_issues,
            count_issues,
            n_prs,
            count_prs,
        )

    except (RateLimitException, ConnectionException) as e:
        logger.error("sync_issues_and_prs: failed for repo id=%s: %s", repo.pk, e)
        raise
    except Exception as e:
        logger.exception(
            "sync_issues_and_prs: unexpected error for repo id=%s: %s",
            repo.pk,
            e,
        )
        raise

    return {"issues": issue_numbers, "pull_requests": pr_numbers}
