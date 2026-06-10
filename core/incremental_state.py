"""Shared :class:`~core.protocols.IncrementalState` implementation for collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class GenericIncrementalState:
    """Default frozen DTO satisfying :class:`~core.protocols.IncrementalState`."""

    checkpoint_token: str | None
    human_readable_marker: str | None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extras", MappingProxyType(dict(self.extras)))
