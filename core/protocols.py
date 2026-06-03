"""
Portable DTO protocols for tracker sync and collection boundaries.

These types complement **orchestration** protocols in :mod:`core.collectors`
(e.g. :class:`~core.collectors.base_collector.CollectorRunnable`), which describe
**how** a management command runs phases. Here we describe **what** crosses layer
and app boundaries: run outcomes, activity events before ORM persistence, and
incremental checkpoints.

Implementations should be small frozen :class:`dataclasses.dataclass` types in each
tracker app. Prefer them over plain ``dict`` for :func:`isinstance` checks with
``@runtime_checkable`` — dict instances do not reliably satisfy attribute-based
protocols at runtime. Attributes on these protocols are read-only ``@property``
stubs so frozen dataclasses (and Pyright) treat implementations as structurally
compatible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable

from core.activity_types import ActivityType, ActorExternalId, SourceSystem


@runtime_checkable
class TrackerResult(Protocol):
    """Outcome of one logical collection or sync cycle."""

    @property
    def success(self) -> bool: ...

    @property
    def counts(self) -> Mapping[str, int]: ...


@runtime_checkable
class ActivityRecord(Protocol):
    """Portable activity event (not a Django model)."""

    @property
    def source_system(self) -> SourceSystem: ...

    @property
    def external_id(self) -> str: ...

    @property
    def occurred_at(self) -> datetime | None: ...

    @property
    def activity_type(self) -> ActivityType: ...

    @property
    def actor_external_id(self) -> ActorExternalId: ...

    @property
    def source_url(self) -> str | None: ...

    @property
    def summary(self) -> str: ...


@runtime_checkable
class IncrementalState(Protocol):
    """Serializable checkpoint between runs (opaque token + human marker + extras)."""

    @property
    def checkpoint_token(self) -> str | None: ...

    @property
    def human_readable_marker(self) -> str | None: ...

    @property
    def extras(self) -> Mapping[str, Any]: ...


def require_tracker_result(obj: object) -> TrackerResult:
    """Return *obj* if it satisfies :class:`TrackerResult`; else raise ``TypeError``."""
    if not isinstance(obj, TrackerResult):
        raise TypeError(f"expected TrackerResult, got {type(obj).__name__!r}")
    return obj


def require_activity_record(obj: object) -> ActivityRecord:
    """Return *obj* if it satisfies :class:`ActivityRecord`; else raise ``TypeError``."""
    if not isinstance(obj, ActivityRecord):
        raise TypeError(f"expected ActivityRecord, got {type(obj).__name__!r}")
    return obj
