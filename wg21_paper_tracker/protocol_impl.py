"""Frozen DTOs implementing :mod:`core.protocols` for WG21 paper tracker."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import TrackerResultDataclass
from wg21_paper_tracker.pipeline import TrackerPipelineResult


@dataclass(frozen=True, repr=False)
class Wg21PaperTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for pipeline outcomes."""

    @classmethod
    def from_pipeline(cls, result: TrackerPipelineResult) -> Wg21PaperTrackerResult:
        n = result.new_paper_count
        return cls(success=True, counts={"new_papers": n})

    @classmethod
    def dry_run(cls) -> Wg21PaperTrackerResult:
        return cls(success=True, counts={})
