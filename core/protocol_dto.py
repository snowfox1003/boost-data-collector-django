"""
Shared frozen dataclass bases with canonical serialization for protocol DTOs.

Concrete tracker implementations subclass :class:`TrackerResultDataclass`,
:class:`IncrementalStateDataclass`, and :class:`ActivityRecordDataclass` to inherit
``asdict()``, ``to_json()``, ``from_dict()``, and log-friendly ``__repr__``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Self

from core.activity_types import (
    ActivityType,
    ActorExternalId,
    SourceSystem,
    actor_external_id,
    ensure_activity_occurred_at,
    format_occurred_at_z,
    parse_activity_occurred_at,
)

_REPR_SUMMARY_MAX = 60
_REPR_MAP_MAX_KEYS = 5
_REPR_ERROR_MAX_ITEMS = 2
_REPR_ERROR_ITEM_MAX = 80


def _json_safe(value: Any) -> Any:
    """Recursively convert a value to JSON-serializable primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return format_occurred_at_z(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ActivityType):
        return str(value)
    if isinstance(value, Mapping):
        return _sorted_dict({str(k): _json_safe(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _sorted_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Return *d* with sorted keys and JSON-safe values."""
    return {k: _json_safe(v) for k, v in sorted(d.items())}


def _repr_mapping(mapping: Mapping[str, Any], *, name: str) -> str:
    items = dict(mapping)
    if len(items) <= _REPR_MAP_MAX_KEYS:
        return f"{name}={items!r}"
    preview = {k: items[k] for k in sorted(items)[:2]}
    return f"{name}={preview!r} <{len(items)} keys>"


def _repr_errors(errors: Sequence[str]) -> str:
    if not errors:
        return "errors=()"
    if len(errors) <= _REPR_ERROR_MAX_ITEMS and all(
        len(e) <= _REPR_ERROR_ITEM_MAX for e in errors
    ):
        return f"errors={tuple(errors)!r}"
    return f"errors=<{len(errors)} items>"


def _truncate_summary(summary: str) -> str:
    if len(summary) <= _REPR_SUMMARY_MAX:
        return summary
    return summary[: _REPR_SUMMARY_MAX - 3] + "..."


@dataclass(frozen=True)
class TrackerResultDataclass:
    """Frozen base for :class:`~core.protocols.TrackerResult` implementations."""

    success: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

    def asdict(self) -> dict[str, Any]:
        return _sorted_dict(
            {
                "success": self.success,
                "counts": dict(self.counts),
                "errors": list(self.errors),
                "duration_seconds": self.duration_seconds,
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.asdict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw_errors = data.get("errors") or []
        return cls(
            success=bool(data["success"]),
            counts={str(k): int(v) for k, v in dict(data["counts"]).items()},
            errors=tuple(str(e) for e in raw_errors),
            duration_seconds=data.get("duration_seconds"),
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"success={self.success!r}, "
            f"{_repr_mapping(self.counts, name='counts')}, "
            f"{_repr_errors(self.errors)}, "
            f"duration_seconds={self.duration_seconds!r})"
        )


@dataclass(frozen=True)
class IncrementalStateDataclass:
    """Frozen base for :class:`~core.protocols.IncrementalState` implementations."""

    checkpoint_token: str | None
    human_readable_marker: str | None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extras", MappingProxyType(dict(self.extras)))

    def asdict(self) -> dict[str, Any]:
        return _sorted_dict(
            {
                "checkpoint_token": self.checkpoint_token,
                "human_readable_marker": self.human_readable_marker,
                "extras": _json_safe(dict(self.extras)),
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.asdict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw_extras = data.get("extras") or {}
        return cls(
            checkpoint_token=data.get("checkpoint_token"),
            human_readable_marker=data.get("human_readable_marker"),
            extras=dict(raw_extras),
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"checkpoint_token={self.checkpoint_token!r}, "
            f"human_readable_marker={self.human_readable_marker!r}, "
            f"{_repr_mapping(self.extras, name='extras')})"
        )


@dataclass(frozen=True)
class ActivityRecordDataclass:
    """Frozen base for :class:`~core.protocols.ActivityRecord` implementations."""

    source_system: SourceSystem
    external_id: str
    occurred_at: datetime | None
    activity_type: ActivityType
    actor_external_id: ActorExternalId
    source_url: str | None
    summary: str

    def __post_init__(self) -> None:
        if self.occurred_at is not None:
            object.__setattr__(
                self, "occurred_at", ensure_activity_occurred_at(self.occurred_at)
            )

    def asdict(self) -> dict[str, Any]:
        occurred = (
            format_occurred_at_z(self.occurred_at)
            if self.occurred_at is not None
            else None
        )
        return _sorted_dict(
            {
                "source_system": self.source_system.value,
                "external_id": self.external_id,
                "occurred_at": occurred,
                "activity_type": str(self.activity_type),
                "actor_external_id": str(self.actor_external_id),
                "source_url": self.source_url,
                "summary": self.summary,
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.asdict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw_occurred = data.get("occurred_at")
        occurred: datetime | None
        if raw_occurred is None:
            occurred = None
        elif isinstance(raw_occurred, datetime):
            occurred = ensure_activity_occurred_at(raw_occurred)
        else:
            text = str(raw_occurred).strip()
            occurred = parse_activity_occurred_at(text) if text else None
        return cls(
            source_system=SourceSystem(str(data["source_system"])),
            external_id=str(data["external_id"]),
            occurred_at=occurred,
            activity_type=ActivityType.parse(str(data["activity_type"])),
            actor_external_id=actor_external_id(data.get("actor_external_id")),
            source_url=data.get("source_url"),
            summary=str(data["summary"]),
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"source_system={self.source_system!r}, "
            f"external_id={self.external_id!r}, "
            f"occurred_at={self.occurred_at!r}, "
            f"activity_type={self.activity_type!r}, "
            f"actor_external_id={self.actor_external_id!r}, "
            f"source_url={self.source_url!r}, "
            f"summary={_truncate_summary(self.summary)!r})"
        )
