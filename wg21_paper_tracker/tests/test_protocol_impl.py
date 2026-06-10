"""Tests for :mod:`wg21_paper_tracker.protocol_impl`."""

from core.protocols import TrackerResult

from wg21_paper_tracker.pipeline import TrackerPipelineResult
from wg21_paper_tracker.protocol_impl import Wg21PaperTrackerResult


def test_wg21_paper_tracker_result_from_pipeline() -> None:
    r = Wg21PaperTrackerResult.from_pipeline(
        TrackerPipelineResult(new_paper_urls=("https://x",))
    )
    assert isinstance(r, TrackerResult)
    assert r.counts["new_papers"] == 1
