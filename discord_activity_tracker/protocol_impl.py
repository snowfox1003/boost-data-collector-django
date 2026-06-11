"""Frozen DTOs implementing :mod:`core.protocols` for Discord activity sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from core.activity_types import (
    ActivityType,
    LegacyActivityRecordDict,
    SourceSystem,
    activity_record_to_legacy_dict,
    migrate_legacy_activity_fields,
)
from core.protocol_dto import (
    ActivityRecordDataclass,
    IncrementalStateDataclass,
    TrackerResultDataclass,
)


@dataclass(frozen=True, repr=False)
class DiscordCollectionTrackerResult(TrackerResultDataclass):
    """Counts for a Discord collection slice (messages, channels, etc.)."""


@dataclass(frozen=True, repr=False)
class DiscordIncrementalState(IncrementalStateDataclass):
    """Checkpoint between Discord runs (after-cursor + optional snowflake)."""

    @classmethod
    def from_after_date(
        cls,
        *,
        after: datetime | None,
        last_message_id: int | None = None,
        channel_id: int | None = None,
    ) -> DiscordIncrementalState:
        marker = after.isoformat() if after is not None else ""
        tok_parts = ["discord"]
        if channel_id is not None:
            tok_parts.append(f"ch:{channel_id}")
        if last_message_id is not None:
            tok_parts.append(f"msg:{last_message_id}")
        checkpoint = ":".join(tok_parts)
        return cls(
            checkpoint_token=checkpoint,
            human_readable_marker=marker or None,
            extras={
                "after_iso": marker,
                "last_message_id": last_message_id,
                "channel_id": channel_id,
            },
        )


@dataclass(frozen=True, repr=False)
class DiscordActivityRecord(ActivityRecordDataclass):
    """Normalized Discord message as a portable activity row."""

    def to_legacy_dict(self) -> LegacyActivityRecordDict:
        """Tier-C workspace bridge format; prefer :meth:`asdict` for canonical protocol JSON."""
        return activity_record_to_legacy_dict(
            source_system=self.source_system,
            external_id=self.external_id,
            occurred_at=self.occurred_at,
            activity_type=self.activity_type,
            actor_id=self.actor_external_id,
            source_url=self.source_url,
            summary=self.summary,
        )

    @classmethod
    def from_converted_export_dict(
        cls,
        converted: Mapping[str, Any],
        *,
        server_id: int,
        channel_id: int,
    ) -> DiscordActivityRecord:
        mid = int(converted.get("id") or 0)
        author = converted.get("author") or {}
        if isinstance(author, Mapping):
            aid = author.get("id")
            actor_raw: str | int | None = aid if aid is not None else ""
        else:
            actor_raw = ""
        occurred_raw = converted.get("occurred_at") or converted.get("created_at") or ""
        content = str(converted.get("content") or "")
        summary = content[:2000]
        ext_id = f"{server_id}:{channel_id}:{mid}"
        src = converted.get("source_url")
        source_url = str(src) if src else None
        mtype = str(converted.get("message_type") or "Default")
        source, occurred, atype, actor = migrate_legacy_activity_fields(
            source_system=SourceSystem.DISCORD.value,
            occurred_at=occurred_raw,
            activity_type=ActivityType.discord_message(mtype),
            actor_external_id_raw=actor_raw,
        )
        return cls(
            source_system=source,
            external_id=ext_id,
            occurred_at=occurred,
            activity_type=atype,
            actor_external_id=actor,
            source_url=source_url,
            summary=summary,
        )
