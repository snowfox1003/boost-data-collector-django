"""Frozen DTOs implementing :mod:`core.protocols` for usage dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class UsageDashboardTrackerResult:
    """Structured :class:`~core.protocols.TrackerResult` for dashboard runs."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    @classmethod
    def from_stats(cls, stats: Mapping[str, Any] | None) -> UsageDashboardTrackerResult:
        if stats is None:
            return cls(success=True, counts={})
        repos = int(stats.get("repos_analyzed") or stats.get("total_repos") or 0)
        return cls(success=True, counts={"repos_analyzed": repos})

    @classmethod
    def skipped(cls) -> UsageDashboardTrackerResult:
        return cls(success=True, counts={})
