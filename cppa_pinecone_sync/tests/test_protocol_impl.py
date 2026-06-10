"""Tests for :mod:`cppa_pinecone_sync.protocol_impl`."""

from core.protocols import TrackerResult

from cppa_pinecone_sync.protocol_impl import PineconeSyncTrackerResult


def test_pinecone_sync_tracker_result_from_sync_dict() -> None:
    r = PineconeSyncTrackerResult.from_sync_dict(
        {"upserted": 2, "total": 3, "failed_count": 1, "errors": ["x"]}
    )
    assert isinstance(r, TrackerResult)
    assert r.counts["upserted"] == 2
    assert r.counts["failed_count"] == 1
    assert r.errors == ("x",)
    assert r.success is False
