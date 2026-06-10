"""Tests for :mod:`boost_mailing_list_tracker.protocol_impl`."""

from core.protocols import IncrementalState, TrackerResult

from boost_mailing_list_tracker.protocol_impl import (
    MailingListIncrementalState,
    MailingListTrackerResult,
)


def test_mailing_list_tracker_result() -> None:
    r = MailingListTrackerResult.from_run(fetched=5, created=2, skipped=1)
    assert isinstance(r, TrackerResult)


def test_mailing_list_incremental_state() -> None:
    st = MailingListIncrementalState.from_start_date("2024-06-01")
    assert isinstance(st, IncrementalState)
