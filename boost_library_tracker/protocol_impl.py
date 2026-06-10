"""Frozen DTOs implementing :mod:`core.protocols` for boost library tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class CollectBoostLibrariesResult:
    """Structured :class:`~core.protocols.TrackerResult` for library metadata collection."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

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
