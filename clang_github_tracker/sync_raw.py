"""
Sync llvm/llvm-project to raw/github_activity_tracker and clang_github_tracker DB.

Staging: JSON is written under workspace/github_activity_tracker/<owner>/<repo>/
(commits|issues|prs). After a successful DB upsert and raw write, the staging file is
removed. On any processing error the staging file is left for the next run.
Pending staging files are processed before any API fetch.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, cast

from github_activity_tracker.api_schemas import (
    GitHubCommit,
    GitHubIssueBundle,
    GitHubPullRequestBundle,
)
from github_activity_tracker.sync_api import (
    fetcher,
    get_commit_json_path,
    get_issue_json_path,
    get_pr_json_path,
    iter_existing_commit_jsons,
    iter_existing_issue_jsons,
    iter_existing_pr_jsons,
    normalize_issue_json,
    normalize_pr_json,
    save_commit_raw_source,
    save_issue_raw_source,
    save_pr_raw_source,
)

from core.utils.datetime_parsing import parse_iso_datetime as parse_datetime
from core.operations.github_ops import get_github_client
from core.operations.github_ops.client import ConnectionException, RateLimitException

from clang_github_tracker import services as clang_services
from clang_github_tracker.workspace import OWNER, REPO

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Return dt converted to UTC if aware, or set to UTC if naive."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _issue_bundle_to_storage_dict(bundle: GitHubIssueBundle) -> dict:
    detail = bundle.issue.model_dump()
    comments = detail.pop("comments", [])
    return {"issue_info": detail, "comments": comments}


def _pr_bundle_to_storage_dict(bundle: GitHubPullRequestBundle) -> dict:
    detail = bundle.pr.model_dump()
    comments = detail.pop("comments", [])
    reviews = detail.pop("reviews", [])
    return {"pr_info": detail, "comments": comments, "reviews": reviews}


def _validated_issue_number(num: object) -> int | None:
    if isinstance(num, str) and num.isdigit():
        num = int(num)
    if not _valid_positive_issue_number(num):
        return None
    return cast(int, num)


def _pr_number_from_dict(item: dict) -> int | None:
    pr_info = item.get("pr_info")
    pr_number = (
        pr_info.get("number") if isinstance(pr_info, dict) else item.get("number")
    )
    return _validated_issue_number(pr_number)


def _is_pr_dict(item: dict) -> bool:
    return "pr_info" in item or "pull_request" in item or "reviews" in item


def _issue_number_from_dict(item: dict) -> int | None:
    issue_number = (item.get("issue_info") or {}).get("number") or item.get("number")
    if issue_number is None:
        return None
    if isinstance(issue_number, str) and issue_number.isdigit():
        issue_number = int(issue_number)
    return _validated_issue_number(issue_number)


def _promote_pr_item(
    owner: str,
    repo: str,
    storage: dict,
    pr_number: int,
    pr_numbers: list[int],
) -> None:
    staging_path = get_pr_json_path(owner, repo, pr_number)
    _write_staging_json(staging_path, storage)
    num_int = _validated_issue_number(normalize_pr_json(storage).get("number"))
    if _promote_pr_staging(owner, repo, staging_path, storage) and num_int is not None:
        pr_numbers.append(num_int)


def _promote_issue_item(
    owner: str,
    repo: str,
    storage: dict,
    issue_number: int,
    issue_numbers: list[int],
) -> None:
    staging_path = get_issue_json_path(owner, repo, issue_number)
    _write_staging_json(staging_path, storage)
    num_int = _validated_issue_number(normalize_issue_json(storage).get("number"))
    if _promote_issue_staging(owner, repo, staging_path, storage) and (
        num_int is not None
    ):
        issue_numbers.append(num_int)


def _valid_positive_issue_number(n: object) -> bool:
    """True for a positive issue/PR number; rejects ``bool`` (``type(n) is int``)."""
    return type(n) is int and n > 0


def commit_date(commit_data: dict) -> datetime | None:
    """Extract author/committer date from GitHub commit payload."""
    commit = commit_data.get("commit") or {}
    author = commit.get("author") or commit.get("committer") or {}
    date_str = author.get("date") or ""
    if not date_str:
        return None
    return parse_datetime(date_str)


def _write_staging_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _promote_commit_staging(
    owner: str, repo: str, staging_path: Path, commit_data: dict
) -> bool:
    """
    Upsert commit to DB, write raw JSON, remove staging file.

    Returns True if fully successful. On failure the staging file is kept (except
    when the payload cannot be processed — invalid sha — staging is removed).
    """
    sha = commit_data.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        logger.warning(
            "clang sync: drop staging commit (missing sha): %s", staging_path
        )
        staging_path.unlink(missing_ok=True)
        return False
    committed_at = commit_date(commit_data)
    try:
        clang_services.upsert_commit(
            str(sha).strip(),
            github_committed_at=committed_at,
        )
    except Exception as e:
        logger.warning(
            "clang sync: commit DB upsert failed, keeping staging %s: %s",
            staging_path,
            e,
        )
        return False
    try:
        save_commit_raw_source(owner, repo, commit_data)
    except Exception:
        logger.exception(
            "clang sync: raw write failed after DB upsert, keeping staging %s",
            staging_path,
        )
        return False
    staging_path.unlink(missing_ok=True)
    return True


def _promote_issue_staging(
    owner: str, repo: str, staging_path: Path, item: dict
) -> bool:
    flat = normalize_issue_json(item)
    num_int = _validated_issue_number(flat.get("number"))
    if num_int is None:
        logger.warning(
            "clang sync: drop staging issue (invalid number): %s", staging_path
        )
        staging_path.unlink(missing_ok=True)
        return False
    try:
        clang_services.upsert_issue_item(
            num_int,
            is_pull_request=False,
            github_created_at=parse_datetime(flat.get("created_at")),
            github_updated_at=parse_datetime(flat.get("updated_at")),
        )
    except Exception as e:
        logger.warning(
            "clang sync: issue DB upsert failed, keeping staging %s: %s",
            staging_path,
            e,
        )
        return False
    try:
        save_issue_raw_source(owner, repo, item)
    except Exception:
        logger.exception(
            "clang sync: issue raw write failed after DB upsert, keeping staging %s",
            staging_path,
        )
        return False
    staging_path.unlink(missing_ok=True)
    return True


def _promote_pr_staging(owner: str, repo: str, staging_path: Path, item: dict) -> bool:
    flat = normalize_pr_json(item)
    num_int = _validated_issue_number(flat.get("number"))
    if num_int is None:
        logger.warning("clang sync: drop staging PR (invalid number): %s", staging_path)
        staging_path.unlink(missing_ok=True)
        return False
    try:
        clang_services.upsert_issue_item(
            num_int,
            is_pull_request=True,
            github_created_at=parse_datetime(flat.get("created_at")),
            github_updated_at=parse_datetime(flat.get("updated_at")),
        )
    except Exception as e:
        logger.warning(
            "clang sync: PR DB upsert failed, keeping staging %s: %s",
            staging_path,
            e,
        )
        return False
    try:
        save_pr_raw_source(owner, repo, item)
    except Exception:
        logger.exception(
            "clang sync: PR raw write failed after DB upsert, keeping staging %s",
            staging_path,
        )
        return False
    staging_path.unlink(missing_ok=True)
    return True


def process_pending_clang_staging(
    owner: str,
    repo: str,
) -> tuple[int, list[int], list[int]]:
    """
    Process workspace/github_activity_tracker/<owner>/<repo>/ commits, issues, prs.

    Returns (commits_promoted, issue_numbers, pr_numbers) for successful promotions.
    """
    commits_promoted = 0
    issue_numbers: list[int] = []
    pr_numbers: list[int] = []

    for path in sorted(iter_existing_commit_jsons(owner, repo), key=lambda p: p.name):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("clang sync: unreadable staging commit %s", path)
            continue
        if not isinstance(data, dict):
            continue
        if _promote_commit_staging(owner, repo, path, data):
            commits_promoted += 1

    for path in sorted(iter_existing_issue_jsons(owner, repo), key=lambda p: p.name):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("clang sync: unreadable staging issue %s", path)
            continue
        if not isinstance(data, dict):
            continue
        flat = normalize_issue_json(data)
        num = flat.get("number")
        num_int = _validated_issue_number(num)
        if _promote_issue_staging(owner, repo, path, data) and num_int is not None:
            issue_numbers.append(num_int)

    for path in sorted(iter_existing_pr_jsons(owner, repo), key=lambda p: p.name):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("clang sync: unreadable staging PR %s", path)
            continue
        if not isinstance(data, dict):
            continue
        flat = normalize_pr_json(data)
        num = flat.get("number")
        num_int = _validated_issue_number(num)
        if _promote_pr_staging(owner, repo, path, data) and num_int is not None:
            pr_numbers.append(num_int)

    return commits_promoted, issue_numbers, pr_numbers


def sync_clang_github_activity(
    start_commit: datetime | None = None,
    start_item: datetime | None = None,
    end_date: Optional[datetime] = None,
) -> tuple[int, list[int], list[int]]:
    """
    Fetch llvm/llvm-project commits, issues, PRs from GitHub and upsert DB rows.

    Staging JSON lives under ``workspace/github_activity_tracker/<owner>/<repo>/``;
    after a successful DB upsert and raw write under
    ``workspace/raw/github_activity_tracker/...``, staging files are removed.
    Pending staging files are processed before any API fetch.

    Args:
        start_commit: Start date for commits (None = from beginning).
        start_item: Single lower bound for unified issues+PRs ``/issues`` fetch.
        end_date: End date for all (default: None = sync through now).

    Returns:
        (commits_saved, issue_numbers, pr_numbers).
    """

    owner = OWNER
    repo = REPO
    end_date = _ensure_utc(end_date)
    start_commit = _ensure_utc(start_commit)
    start_item = _ensure_utc(start_item)

    client = get_github_client(use="scraping")
    if client is None:
        raise RuntimeError("GitHub client unavailable for clang sync")

    pending_c, pending_i, pending_p = process_pending_clang_staging(owner, repo)
    commits_saved = pending_c
    issue_numbers: list[int] = list(pending_i)
    pr_numbers: list[int] = list(pending_p)

    try:
        for commit in fetcher.fetch_commits_from_github(
            client, owner, repo, start_commit, end_date
        ):
            commit_data = (
                commit.model_dump() if isinstance(commit, GitHubCommit) else commit
            )
            sha = commit_data.get("sha")
            if not isinstance(sha, str) or not sha.strip():
                continue
            sha_clean = sha.strip()
            staging_path = get_commit_json_path(owner, repo, sha_clean)
            _write_staging_json(staging_path, commit_data)
            if _promote_commit_staging(owner, repo, staging_path, commit_data):
                commits_saved += 1

        for item in fetcher.fetch_issues_and_prs_from_github(
            client, owner, repo, start_item, end_date
        ):
            if isinstance(item, GitHubPullRequestBundle):
                pr_number = item.pr.number
                if pr_number is None:
                    continue
                _promote_pr_item(
                    owner,
                    repo,
                    _pr_bundle_to_storage_dict(item),
                    pr_number,
                    pr_numbers,
                )
            elif isinstance(item, dict) and _is_pr_dict(item):
                pr_number = _pr_number_from_dict(item)
                if pr_number is None:
                    continue
                _promote_pr_item(owner, repo, item, pr_number, pr_numbers)
            else:
                if isinstance(item, GitHubIssueBundle):
                    issue_number = item.issue.number
                    if issue_number is None:
                        continue
                    _promote_issue_item(
                        owner,
                        repo,
                        _issue_bundle_to_storage_dict(item),
                        issue_number,
                        issue_numbers,
                    )
                elif isinstance(item, dict):
                    issue_number = _issue_number_from_dict(item)
                    if issue_number is None:
                        continue
                    _promote_issue_item(owner, repo, item, issue_number, issue_numbers)

    except (ConnectionException, RateLimitException) as e:
        logger.exception("clang_github_tracker sync failed: %s", e)
        raise

    return commits_saved, issue_numbers, pr_numbers
