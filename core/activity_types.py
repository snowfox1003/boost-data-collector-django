"""
Typed field helpers for :class:`~core.protocols.ActivityRecord`.

Bridges legacy string-keyed export/bridge payloads and timezone-aware
:class:`datetime.datetime` values used on frozen tracker dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import NewType, TypedDict

from core.utils.datetime_parsing import ensure_aware_utc, parse_iso_datetime_lenient

ActorExternalId = NewType("ActorExternalId", str)


class SourceSystem(StrEnum):
    """Origin system for a portable activity row."""

    GITHUB = "github"
    DISCORD = "discord"


@dataclass(frozen=True, slots=True)
class ActivityType:
    """Branded activity classifier (e.g. ``github.issue``, ``discord.Reply``)."""

    value: str

    def __str__(self) -> str:
        return self.value

    @classmethod
    def github_issue(cls) -> ActivityType:
        return cls("github.issue")

    @classmethod
    def discord_message(cls, subtype: str) -> ActivityType:
        return cls(f"discord.{subtype or 'Default'}")

    @classmethod
    def parse(cls, raw: str | ActivityType) -> ActivityType:
        if isinstance(raw, ActivityType):
            return raw
        return cls(str(raw).strip())


class LegacyActivityRecordDict(TypedDict):
    """String-keyed activity row for export/bridge JSON."""

    source_system: str
    external_id: str
    occurred_at: str
    activity_type: str
    actor_external_id: str
    source_url: str | None
    summary: str


def actor_external_id(raw: str | int | None) -> ActorExternalId:
    """Coerce a legacy actor id to :data:`ActorExternalId`."""
    if raw is None:
        return ActorExternalId("")
    return ActorExternalId(str(raw).strip())


def parse_activity_occurred_at(raw: str) -> datetime | None:
    """Parse an ISO-like instant; return timezone-aware UTC or ``None``."""
    dt = parse_iso_datetime_lenient(raw)
    if dt is None:
        return None
    return ensure_aware_utc(dt)


def ensure_activity_occurred_at(dt: datetime) -> datetime:
    """Return *dt* as timezone-aware UTC."""
    normalized = ensure_aware_utc(dt)
    assert normalized is not None
    return normalized


def _parse_source_system(raw: str) -> SourceSystem:
    text = str(raw).strip().lower()
    try:
        return SourceSystem(text)
    except ValueError as exc:
        raise ValueError(f"unknown source_system: {raw!r}") from exc


def _parse_occurred_at(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return ensure_activity_occurred_at(raw)
    text = str(raw).strip()
    if not text:
        return None
    return parse_activity_occurred_at(text)


def format_occurred_at_z(dt: datetime) -> str:
    """Serialize *dt* as timezone-aware UTC ISO-8601 with ``Z`` suffix."""
    aware = ensure_activity_occurred_at(dt)
    return aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def migrate_legacy_activity_fields(
    *,
    source_system: str,
    occurred_at: str | datetime | None,
    activity_type: str | ActivityType,
    actor_external_id_raw: str | int | None,
) -> tuple[SourceSystem, datetime | None, ActivityType, ActorExternalId]:
    """Normalize legacy string fields to typed ActivityRecord components."""
    return (
        _parse_source_system(source_system),
        _parse_occurred_at(occurred_at),
        ActivityType.parse(activity_type),
        actor_external_id(actor_external_id_raw),
    )


def activity_record_to_legacy_dict(
    *,
    source_system: SourceSystem,
    external_id: str,
    occurred_at: datetime | None,
    activity_type: ActivityType,
    actor_id: ActorExternalId,
    source_url: str | None,
    summary: str,
) -> LegacyActivityRecordDict:
    """Serialize typed activity fields to string-keyed export/bridge JSON."""
    occurred_str = format_occurred_at_z(occurred_at) if occurred_at is not None else ""
    return LegacyActivityRecordDict(
        source_system=source_system.value,
        external_id=external_id,
        occurred_at=occurred_str,
        activity_type=str(activity_type),
        actor_external_id=str(actor_id),
        source_url=source_url,
        summary=summary,
    )
