"""Frozen DTOs implementing :mod:`core.protocols` for boost library tracker."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import TrackerResultDataclass


@dataclass(frozen=True, repr=False)
class CollectBoostLibrariesResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for library metadata collection."""

    @classmethod
    def from_totals(
        cls,
        *,
        versions_created: int,
        library_versions_created: int,
        dry_run: bool = False,
    ) -> CollectBoostLibrariesResult:
        return cls(
            success=True,
            counts={
                "versions": versions_created,
                "library_versions": library_versions_created,
                "dry_run": int(dry_run),
            },
        )

    @classmethod
    def empty(cls, *, dry_run: bool = False) -> CollectBoostLibrariesResult:
        return cls(success=True, counts={"dry_run": int(dry_run)})
