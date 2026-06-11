"""Frozen DTOs implementing :mod:`core.protocols` for usage dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.protocol_dto import TrackerResultDataclass


@dataclass(frozen=True, repr=False)
class UsageDashboardTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for dashboard runs."""

    @classmethod
    def from_stats(cls, stats: Mapping[str, Any] | None) -> UsageDashboardTrackerResult:
        if stats is None:
            return cls(success=True, counts={})
        repos = int(stats.get("repos_analyzed") or stats.get("total_repos") or 0)
        return cls(success=True, counts={"repos_analyzed": repos})

    @classmethod
    def skipped(cls) -> UsageDashboardTrackerResult:
        return cls(success=True, counts={})
