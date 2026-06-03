"""Tests for :mod:`discord_activity_tracker.protocol_impl` and chat_exporter bridge."""

from __future__ import annotations

from core.activity_types import ActivityType, SourceSystem
from core.protocols import ActivityRecord, IncrementalState

from discord_activity_tracker.protocol_impl import (
    DiscordActivityRecord,
    DiscordIncrementalState,
)
from discord_activity_tracker.sync.chat_exporter import (
    exporter_message_to_activity_record,
)


def test_discord_incremental_state_from_after_date():
    st = DiscordIncrementalState.from_after_date(
        after=None, last_message_id=100, channel_id=55
    )
    assert isinstance(st, IncrementalState)
    assert st.extras["channel_id"] == 55


def test_exporter_message_to_activity_record_matches_protocol():
    msg = {
        "id": "12",
        "timestamp": "2024-06-01T12:00:00.0000000+00:00",
        "content": "hello world",
        "type": "Default",
        "author": {"id": "99", "name": "user1"},
        "attachments": [],
        "reactions": [],
    }
    rec = exporter_message_to_activity_record(msg, server_id=1, channel_id=2)
    assert isinstance(rec, ActivityRecord)
    assert rec.external_id == "1:2:12"
    assert "hello" in rec.summary


def test_discord_activity_record_from_converted_export_dict():
    converted = {
        "id": 5,
        "created_at": "2024-01-01T00:00:00.0000000Z",
        "occurred_at": "2024-01-01T00:00:00.0000000Z",
        "message_type": "Reply",
        "content": "x",
        "author": {"id": 7},
        "source_url": "https://discord.com/channels/1/2/5",
    }
    rec = DiscordActivityRecord.from_converted_export_dict(
        converted, server_id=1, channel_id=2
    )
    assert str(rec.actor_external_id) == "7"
    assert rec.activity_type == ActivityType.discord_message("Reply")
    assert rec.source_system is SourceSystem.DISCORD
