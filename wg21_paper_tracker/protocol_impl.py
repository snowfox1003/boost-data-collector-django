"""Frozen DTOs implementing :mod:`core.protocols` for WG21 paper tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from wg21_paper_tracker.pipeline import TrackerPipelineResult


@dataclass(frozen=True)
class Wg21PaperTrackerResult:
    """Structured :class:`~core.protocols.TrackerResult` for pipeline outcomes."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

    @classmethod
    def from_pipeline(cls, result: TrackerPipelineResult) -> Wg21PaperTrackerResult:
        n = result.new_paper_count
        return cls(success=True, counts={"new_papers": n})

    @classmethod
    def dry_run(cls) -> Wg21PaperTrackerResult:
        return cls(success=True, counts={})
