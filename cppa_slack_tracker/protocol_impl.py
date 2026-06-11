"""Frozen DTOs implementing :mod:`core.protocols` for CPPA Slack tracker."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import IncrementalStateDataclass, TrackerResultDataclass


@dataclass(frozen=True, repr=False)
class SlackTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for Slack sync runs."""

    @classmethod
    def from_counts(cls, **counts: int) -> SlackTrackerResult:
        return cls(success=True, counts=dict(counts))

    @classmethod
    def dry_run(cls) -> SlackTrackerResult:
        return cls(success=True, counts={})


@dataclass(frozen=True, repr=False)
class SlackIncrementalState(IncrementalStateDataclass):
    """Checkpoint between Slack message sync runs."""

    @classmethod
    def from_team(
        cls, *, team_id: str, start_date: str | None
    ) -> SlackIncrementalState:
        return cls(
            checkpoint_token=f"slack:team:{team_id}",
            human_readable_marker=start_date,
            extras={"team_id": team_id, "start_date": start_date},
        )
