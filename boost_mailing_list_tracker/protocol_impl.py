"""Frozen DTOs implementing :mod:`core.protocols` for mailing list tracker."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import IncrementalStateDataclass, TrackerResultDataclass


@dataclass(frozen=True, repr=False)
class MailingListTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for mailing list runs."""

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


@dataclass(frozen=True, repr=False)
class MailingListIncrementalState(IncrementalStateDataclass):
    """Checkpoint between mailing list runs."""

    @classmethod
    def from_start_date(cls, start_date: str | None) -> MailingListIncrementalState:
        return cls(
            checkpoint_token="mailing_list:boost",
            human_readable_marker=start_date,
            extras={"start_date": start_date},
        )
