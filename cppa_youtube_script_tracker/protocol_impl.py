"""Frozen DTOs implementing :mod:`core.protocols` for YouTube script tracker."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import TrackerResultDataclass


@dataclass(frozen=True, repr=False)
class YoutubeScriptTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for YouTube runs."""

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
