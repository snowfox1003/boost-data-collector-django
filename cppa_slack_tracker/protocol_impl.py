"""Frozen DTOs implementing :mod:`core.protocols` for CPPA Slack tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class SlackTrackerResult:
    """Structured :class:`~core.protocols.TrackerResult` for Slack sync runs."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

    @classmethod
    def from_counts(cls, **counts: int) -> SlackTrackerResult:
        return cls(success=True, counts=dict(counts))

    @classmethod
    def dry_run(cls) -> SlackTrackerResult:
        return cls(success=True, counts={})


@dataclass(frozen=True)
class SlackIncrementalState:
    """Checkpoint between Slack message sync runs."""

    checkpoint_token: str | None
    human_readable_marker: str | None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extras", MappingProxyType(dict(self.extras)))

    @classmethod
    def from_team(
        cls, *, team_id: str, start_date: str | None
    ) -> SlackIncrementalState:
        return cls(
            checkpoint_token=f"slack:team:{team_id}",
            human_readable_marker=start_date,
            extras={"team_id": team_id, "start_date": start_date},
        )
