"""Frozen DTOs implementing :mod:`core.protocols` for Discord activity sync."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class DiscordCollectionTrackerResult:
    """Counts for a Discord collection slice (messages, channels, etc.)."""

    success: bool
    counts: Mapping[str, int]


@dataclass(frozen=True)
class DiscordIncrementalState:
    """Checkpoint between Discord runs (after-cursor + optional snowflake)."""

    checkpoint_token: str | None
    human_readable_marker: str | None
    extras: Mapping[str, Any] = field(default_factory=dict)

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


@dataclass(frozen=True)
class DiscordActivityRecord:
    """Normalized Discord message as a portable activity row."""

    source_system: str
    external_id: str
    occurred_at: str
    activity_type: str
    actor_external_id: str
    source_url: str | None
    summary: str

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
            actor = str(aid) if aid is not None else ""
        else:
            actor = ""
        occurred = str(
            converted.get("occurred_at") or converted.get("created_at") or ""
        )
        content = str(converted.get("content") or "")
        summary = content[:2000]
        ext_id = f"{server_id}:{channel_id}:{mid}"
        src = converted.get("source_url")
        source_url = str(src) if src else None
        mtype = str(converted.get("message_type") or "Default")
        return cls(
            source_system="discord",
            external_id=ext_id,
            occurred_at=occurred,
            activity_type=f"discord.{mtype}",
            actor_external_id=actor,
            source_url=source_url,
            summary=summary,
        )
