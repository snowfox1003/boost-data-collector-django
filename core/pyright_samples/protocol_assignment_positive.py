"""Pyright-positive sample: structural conformance to :class:`core.protocols.TrackerResult`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from core.protocols import TrackerResult


@dataclass(frozen=True)
class _LocalTrackerResult:
    success: bool
    counts: Mapping[str, int]


def sample_tracker_result() -> TrackerResult:
    return _LocalTrackerResult(success=True, counts={"items": 0})
