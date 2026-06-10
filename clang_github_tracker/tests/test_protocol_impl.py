"""Tests for :mod:`clang_github_tracker.protocol_impl`."""

from core.protocols import IncrementalState, TrackerResult

from clang_github_tracker.protocol_impl import (
    ClangGithubIncrementalState,
    ClangGithubTrackerResult,
)


def test_clang_tracker_result_from_sync() -> None:
    r = ClangGithubTrackerResult.from_sync(
        commits_saved=1, issue_count=2, pr_count=3, md_files=4
    )
    assert isinstance(r, TrackerResult)
    assert r.counts["commits"] == 1


def test_clang_incremental_state() -> None:
    st = ClangGithubIncrementalState.from_watermarks(start_commit="c", start_item="i")
    assert isinstance(st, IncrementalState)
