"""Merge DiscordChatExporter JSON into per-day raw archives."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.utils.datetime_parsing import parse_iso_datetime_lenient

logger = logging.getLogger(__name__)


def message_utc_date_str(msg: dict[str, Any]) -> str | None:
    """Return ``YYYY-MM-DD`` (UTC) for an exporter message dict, or ``None`` if unparseable."""
    raw_ts = msg.get("timestamp")
    if not raw_ts:
        return None
    dt = parse_iso_datetime_lenient(str(raw_ts))
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _message_sort_key(msg: dict[str, Any]) -> tuple[str, str]:
    ts = str(msg.get("timestamp") or "")
    mid = str(msg.get("id") or "")
    return (ts, mid)


def _filter_messages_for_day(
    messages: list[dict[str, Any]], day: str
) -> list[dict[str, Any]]:
    return [m for m in messages if message_utc_date_str(m) == day]


def _merge_message_lists(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for msg in existing:
        mid = str(msg.get("id", ""))
        if mid:
            by_id[mid] = msg
    for msg in incoming:
        mid = str(msg.get("id", ""))
        if mid:
            by_id[mid] = msg
    return sorted(by_id.values(), key=_message_sort_key)


def _refresh_envelope_metadata(merged: dict[str, Any]) -> None:
    messages: list[dict[str, Any]] = merged.get("messages") or []
    now_iso = datetime.now(timezone.utc).isoformat()
    merged["exportedAt"] = now_iso

    if not messages:
        date_range = merged.setdefault("dateRange", {})
        if not isinstance(date_range, dict):
            merged["dateRange"] = date_range = {}
        return

    timestamps = []
    for msg in messages:
        dt = parse_iso_datetime_lenient(str(msg.get("timestamp") or ""))
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            timestamps.append(dt)

    if timestamps:
        earliest = min(timestamps)
        latest = max(timestamps)
        merged["dateRange"] = {
            "after": earliest.isoformat(),
            "before": latest.isoformat(),
        }


def merge_exporter_json(dest: Path, incoming: dict[str, Any], *, day: str) -> int:
    """Merge *incoming* exporter JSON into *dest* for UTC calendar day *day*.

    Messages are keyed by snowflake ``id``; incoming overwrites existing entries.
    Only messages on *day* (UTC) are kept in the archive.

    Returns the number of messages written to the merged file.
    """
    incoming_msgs = _filter_messages_for_day(incoming.get("messages") or [], day)

    if dest.is_file():
        with open(dest, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing_msgs = _filter_messages_for_day(existing.get("messages") or [], day)
        merged_msgs = _merge_message_lists(existing_msgs, incoming_msgs)
        merged = dict(existing)
        merged["guild"] = incoming.get("guild") or existing.get("guild") or {}
        merged["channel"] = incoming.get("channel") or existing.get("channel") or {}
    else:
        merged_msgs = _merge_message_lists([], incoming_msgs)
        merged = {
            "guild": incoming.get("guild") or {},
            "channel": incoming.get("channel") or {},
        }

    merged["messages"] = merged_msgs
    _refresh_envelope_metadata(merged)

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json", dir=dest.parent, prefix=f".{dest.stem}."
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, dest)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    logger.debug("Merged %d message(s) into %s", len(merged_msgs), dest)
    return len(merged_msgs)
