"""Frozen DTOs implementing :mod:`core.protocols` for Pinecone sync."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class PineconeSyncTrackerResult:
    """Structured :class:`~core.protocols.TrackerResult` for ``sync_to_pinecone`` outcomes."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    @classmethod
    def from_sync_dict(cls, d: Mapping[str, Any]) -> PineconeSyncTrackerResult:
        raw_errors = d.get("errors") or []
        errors = tuple(str(e) for e in raw_errors)
        failed = int(d.get("failed_count") or 0)
        return cls(
            success=failed == 0 and not errors,
            counts={
                "upserted": int(d.get("upserted") or 0),
                "total": int(d.get("total") or 0),
                "failed_count": failed,
            },
            errors=errors,
        )
