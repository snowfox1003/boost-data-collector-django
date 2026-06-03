"""Pyright-negative sample: invalid types for :class:`core.protocols.ActivityRecord` fields."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocols import ActivityRecord


@dataclass(frozen=True)
class BrokenActivityRecord:
    source_system: str
    external_id: str
    occurred_at: str
    activity_type: str
    actor_external_id: str
    source_url: str | None
    summary: str


def assign_broken_record() -> ActivityRecord:
    return BrokenActivityRecord(
        source_system="discord",
        external_id="1:2:3",
        occurred_at="2024-01-01T00:00:00Z",
        activity_type="discord.Default",
        actor_external_id="99",
        source_url=None,
        summary="hi",
    )
