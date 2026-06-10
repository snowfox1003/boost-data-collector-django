"""Frozen DTOs implementing :mod:`core.protocols` for YouTube script tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class YoutubeScriptTrackerResult:
    """Structured :class:`~core.protocols.TrackerResult` for YouTube runs."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

    @classmethod
    def from_run(
        cls,
        *,
        videos: int = 0,
        dry_run: bool = False,
    ) -> YoutubeScriptTrackerResult:
        return cls(
            success=True,
            counts={"videos": videos, "dry_run": int(dry_run)},
        )
