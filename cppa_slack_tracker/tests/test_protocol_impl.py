"""Tests for :mod:`cppa_slack_tracker.protocol_impl`."""

from core.protocols import IncrementalState, TrackerResult

from cppa_slack_tracker.protocol_impl import SlackIncrementalState, SlackTrackerResult


def test_slack_tracker_result() -> None:
    r = SlackTrackerResult.from_counts(messages=10, users=5)
    assert isinstance(r, TrackerResult)


def test_slack_incremental_state() -> None:
    st = SlackIncrementalState.from_team(team_id="T", start_date="2024-01-01")
    assert isinstance(st, IncrementalState)
