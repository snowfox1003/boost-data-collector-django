"""
Cross-app GitHub sync and preprocess API.

Other tracker apps (e.g. clang_github_tracker) must import orchestration helpers from
this module only — not ``fetcher``, ``sync.*``, ``workspace``, or ``preprocessors``
directly.

Stability: only symbols in ``__all__`` are Tier A; see STABILITY.md at the repo root.
"""

from __future__ import annotations

from github_activity_tracker import fetcher
from github_activity_tracker.preprocessors.github_preprocess import (
    build_issue_document,
    build_pr_document,
    preprocess_all_issues,
    preprocess_all_prs,
)
from github_activity_tracker.protocol_impl import GitHubSyncTrackerResult
from github_activity_tracker.sync import sync_github
from github_activity_tracker.sync.raw_source import (
    save_commit_raw_source,
    save_issue_raw_source,
    save_pr_raw_source,
)
from github_activity_tracker.sync.utils import (
    normalize_issue_json,
    normalize_pr_json,
)
from github_activity_tracker.workspace import (
    get_commit_json_path,
    get_issue_json_path,
    get_pr_json_path,
    get_raw_source_issue_path,
    get_raw_source_pr_path,
    iter_existing_commit_jsons,
    iter_existing_issue_jsons,
    iter_existing_pr_jsons,
)

__all__ = [
    "GitHubSyncTrackerResult",
    "build_issue_document",
    "build_pr_document",
    "fetcher",
    "get_commit_json_path",
    "get_issue_json_path",
    "get_pr_json_path",
    "get_raw_source_issue_path",
    "get_raw_source_pr_path",
    "iter_existing_commit_jsons",
    "iter_existing_issue_jsons",
    "iter_existing_pr_jsons",
    "normalize_issue_json",
    "normalize_pr_json",
    "preprocess_all_issues",
    "preprocess_all_prs",
    "save_commit_raw_source",
    "save_issue_raw_source",
    "save_pr_raw_source",
    "sync_github",
]
