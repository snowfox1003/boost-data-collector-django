"""Runtime protocol conformance for collector DTO implementations."""

from __future__ import annotations

import pytest

from core.incremental_state import GenericIncrementalState
from core.protocols import IncrementalState, TrackerResult
from core.tracker_result import GenericTrackerResult

from boost_library_docs_tracker.protocol_impl import LibraryDocsTrackerResult
from boost_library_tracker.protocol_impl import CollectBoostLibrariesResult
from boost_library_usage_dashboard.protocol_impl import UsageDashboardTrackerResult
from boost_mailing_list_tracker.protocol_impl import (
    MailingListIncrementalState,
    MailingListTrackerResult,
)
from clang_github_tracker.protocol_impl import (
    ClangGithubIncrementalState,
    ClangGithubTrackerResult,
)
from cppa_pinecone_sync.protocol_impl import PineconeSyncTrackerResult
from cppa_slack_tracker.protocol_impl import SlackIncrementalState, SlackTrackerResult
from cppa_youtube_script_tracker.protocol_impl import YoutubeScriptTrackerResult
from github_activity_tracker.protocol_impl import (
    GitHubIncrementalState,
    GitHubSyncTrackerResult,
)
from wg21_paper_tracker.protocol_impl import Wg21PaperTrackerResult


@pytest.mark.parametrize(
    "result",
    [
        GenericTrackerResult.ok(),
        GitHubSyncTrackerResult(success=True, counts={"issues": 1}),
        PineconeSyncTrackerResult.from_sync_dict(
            {"upserted": 1, "total": 1, "failed_count": 0}
        ),
        UsageDashboardTrackerResult.from_stats({"repos_analyzed": 3}),
        Wg21PaperTrackerResult.dry_run(),
        ClangGithubTrackerResult.dry_run(),
        MailingListTrackerResult.from_run(fetched=1, created=1, skipped=0),
        SlackTrackerResult.dry_run(),
        YoutubeScriptTrackerResult.from_run(videos=1),
        LibraryDocsTrackerResult.from_run(versions=1, pages=5),
        CollectBoostLibrariesResult.empty(),
    ],
)
def test_tracker_result_isinstance(result: TrackerResult) -> None:
    assert isinstance(result, TrackerResult)
    assert result.errors == () or isinstance(result.errors, tuple)


@pytest.mark.parametrize(
    "state",
    [
        GenericIncrementalState(checkpoint_token="t", human_readable_marker="m"),
        GitHubIncrementalState.from_repo_watermark(repo_id=1, marker="2024"),
        MailingListIncrementalState.from_start_date("2024-01-01"),
        SlackIncrementalState.from_team(team_id="T1", start_date="2024-01-01"),
        ClangGithubIncrementalState.from_watermarks(
            start_commit="abc", start_item="2024"
        ),
    ],
)
def test_incremental_state_isinstance(state: IncrementalState) -> None:
    assert isinstance(state, IncrementalState)
