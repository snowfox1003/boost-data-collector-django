"""Frozen DTOs implementing :mod:`core.protocols` for mailing list tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class MailingListTrackerResult:
    """Structured :class:`~core.protocols.TrackerResult` for mailing list runs."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    @classmethod
    def from_run(
        cls,
        *,
        fetched: int,
        created: int,
        skipped: int,
        dry_run: bool = False,
    ) -> MailingListTrackerResult:
        return cls(
            success=True,
            counts={
                "fetched": fetched,
                "created": created,
                "skipped": skipped,
                "dry_run": int(dry_run),
            },
        )


@dataclass(frozen=True)
class MailingListIncrementalState:
    """Checkpoint between mailing list runs."""

    checkpoint_token: str | None
    human_readable_marker: str | None
    extras: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_start_date(cls, start_date: str | None) -> MailingListIncrementalState:
        return cls(
            checkpoint_token="mailing_list:boost",
            human_readable_marker=start_date,
            extras={"start_date": start_date},
        )
