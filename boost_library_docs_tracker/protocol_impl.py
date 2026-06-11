"""Frozen DTOs implementing :mod:`core.protocols` for library docs tracker."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import TrackerResultDataclass


@dataclass(frozen=True, repr=False)
class LibraryDocsTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for docs scrape runs."""

    @classmethod
    def from_run(
        cls,
        *,
        versions: int,
        pages: int = 0,
        dry_run: bool = False,
    ) -> LibraryDocsTrackerResult:
        return cls(
            success=True,
            counts={
                "versions": versions,
                "pages": pages,
                "dry_run": int(dry_run),
            },
        )
