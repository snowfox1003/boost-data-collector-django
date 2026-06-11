"""Shared :class:`~core.protocols.IncrementalState` implementation for collectors."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import IncrementalStateDataclass


@dataclass(frozen=True, repr=False)
class GenericIncrementalState(IncrementalStateDataclass):
    """Default frozen DTO satisfying :class:`~core.protocols.IncrementalState`."""
