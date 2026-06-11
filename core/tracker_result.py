"""Shared :class:`~core.protocols.TrackerResult` implementation for collectors."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from typing import TYPE_CHECKING

from core.protocol_dto import TrackerResultDataclass

if TYPE_CHECKING:
    from core.protocols import TrackerResult


@dataclass(frozen=True, repr=False)
class GenericTrackerResult(TrackerResultDataclass):
    """Default frozen DTO satisfying :class:`~core.protocols.TrackerResult`."""

    @classmethod
    def ok(cls, **counts: int) -> GenericTrackerResult:
        """Build a successful result with the given count fields."""
        return cls(success=True, counts=dict(counts))

    @classmethod
    def failed(cls, *errors: str, **counts: int) -> GenericTrackerResult:
        """Build a failed result with optional error messages and counts."""
        return cls(success=False, counts=dict(counts), errors=tuple(errors))

    def with_duration(self, duration_seconds: float) -> GenericTrackerResult:
        """Return a copy with ``duration_seconds`` set (for framework backfill)."""
        if self.duration_seconds is not None:
            return self
        return replace(self, duration_seconds=duration_seconds)


def with_duration_if_missing(
    result: TrackerResult, duration_seconds: float
) -> TrackerResult:
    """Return *result* unchanged if duration is set; else a copy with duration backfilled."""
    if result.duration_seconds is not None:
        return result
    if isinstance(result, GenericTrackerResult):
        return result.with_duration(duration_seconds)
    if is_dataclass(result) and not isinstance(result, type):
        duration_field = next(
            (f for f in fields(result) if f.name == "duration_seconds"), None
        )
        if duration_field is not None and duration_field.init:
            try:
                return replace(result, duration_seconds=duration_seconds)  # type: ignore[return-value]
            except (TypeError, ValueError):
                return result
    return result
