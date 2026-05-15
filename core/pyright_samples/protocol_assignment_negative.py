"""Pyright-negative sample: invalid return type for :class:`core.protocols.TrackerResult`."""

from __future__ import annotations

from core.protocols import TrackerResult


def broken_tracker_result() -> TrackerResult:
    return "not a TrackerResult"
