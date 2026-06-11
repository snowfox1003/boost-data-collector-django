"""Shared :class:`~core.protocols.ActivityRecord` implementation for collectors."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import ActivityRecordDataclass


@dataclass(frozen=True, repr=False)
class GenericActivityRecord(ActivityRecordDataclass):
    """Default frozen DTO satisfying :class:`~core.protocols.ActivityRecord`."""
