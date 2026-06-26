"""Round-trip and repr tests for protocol DTO serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.activity_record import GenericActivityRecord
from core.activity_types import ActivityType, SourceSystem, actor_external_id
from core.incremental_state import GenericIncrementalState
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
    GitHubActivityRecord,
    GitHubIncrementalState,
    GitHubSyncTrackerResult,
)
from wg21_paper_tracker.protocol_impl import Wg21PaperTrackerResult

_TRACKER_RESULTS = [
    GenericTrackerResult.ok(),
    GenericTrackerResult.failed("oops", items=0),
    GenericTrackerResult(
        success=False,
        counts={"items": 1},
        errors=("e1", "e2"),
        duration_seconds=1.5,
    ),
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
]

_INCREMENTAL_STATES = [
    GenericIncrementalState(checkpoint_token="t", human_readable_marker="m"),
    GitHubIncrementalState.from_repo_watermark(repo_id=1, marker="2024"),
    MailingListIncrementalState.from_start_date("2024-01-01"),
    SlackIncrementalState.from_team(team_id="T1", start_date="2024-01-01"),
    ClangGithubIncrementalState.from_watermarks(start_commit="abc", start_item="2024"),
]

_ACTIVITY_RECORDS = [
    GitHubActivityRecord.from_issue(repo_id=7, issue_number=123, summary="title"),
    GenericActivityRecord(
        source_system=SourceSystem.GITHUB,
        external_id="1:issue:1",
        occurred_at=None,
        activity_type=ActivityType.github_issue(),
        actor_external_id=actor_external_id(""),
        source_url=None,
        summary="x" * 200,
    ),
]


@pytest.mark.parametrize("obj", _TRACKER_RESULTS, ids=lambda o: type(o).__name__)
def test_tracker_result_round_trip(obj) -> None:
    restored = type(obj).from_dict(obj.asdict())
    assert restored == obj
    assert json.loads(obj.to_json()) == obj.asdict()
    json.dumps(obj.asdict())


@pytest.mark.parametrize("obj", _INCREMENTAL_STATES, ids=lambda o: type(o).__name__)
def test_incremental_state_round_trip(obj) -> None:
    restored = type(obj).from_dict(obj.asdict())
    assert restored == obj
    assert json.loads(obj.to_json()) == obj.asdict()
    json.dumps(obj.asdict())


@pytest.mark.parametrize("obj", _ACTIVITY_RECORDS, ids=lambda o: type(o).__name__)
def test_activity_record_round_trip(obj) -> None:
    restored = type(obj).from_dict(obj.asdict())
    assert restored == obj
    assert json.loads(obj.to_json()) == obj.asdict()
    json.dumps(obj.asdict())


@pytest.mark.parametrize(
    "obj", _TRACKER_RESULTS + _INCREMENTAL_STATES + _ACTIVITY_RECORDS
)
def test_to_json_is_deterministic(obj) -> None:
    again = type(obj).from_dict(json.loads(obj.to_json()))
    assert again.to_json() == obj.to_json()


def test_tracker_result_repr_truncates_many_errors() -> None:
    obj = GenericTrackerResult(
        success=False,
        counts={"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6},
        errors=("one", "two", "three"),
    )
    text = repr(obj)
    assert "errors=<3 items>" in text
    assert "counts=" in text
    assert "<6 keys>" in text


def test_activity_record_repr_truncates_summary() -> None:
    obj = GenericActivityRecord(
        source_system=SourceSystem.DISCORD,
        external_id="1:2:3",
        occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        activity_type=ActivityType.discord_message("Default"),
        actor_external_id=actor_external_id("1"),
        source_url=None,
        summary="word " * 50,
    )
    text = repr(obj)
    assert "..." in text
    assert len(text) < 400
