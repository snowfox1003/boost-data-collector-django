"""Tests for :mod:`boost_library_tracker.protocol_impl`."""

from core.protocols import TrackerResult

from boost_library_tracker.protocol_impl import CollectBoostLibrariesResult


def test_collect_boost_libraries_result() -> None:
    r = CollectBoostLibrariesResult.from_totals(
        versions_created=1, library_versions_created=10
    )
    assert isinstance(r, TrackerResult)
