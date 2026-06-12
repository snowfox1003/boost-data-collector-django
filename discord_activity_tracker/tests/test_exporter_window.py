"""Tests for sync/exporter_window.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from cppa_user_tracker.models import DiscordProfile
from discord_activity_tracker.models import (
    DiscordChannel,
    DiscordMessage,
    DiscordServer,
)
from discord_activity_tracker.sync.exporter_window import (
    incremental_export_after,
    iter_channel_export_days,
    latest_message_created_at_for_channel,
    latest_message_created_at_for_guild,
    resolve_channel_export_after,
    utc_day_start,
)


def _uid() -> int:
    return uuid.uuid4().int % (2**50)


@pytest.mark.django_db
def test_latest_message_empty_db():
    assert latest_message_created_at_for_guild(999001, channel_ids=None) is None


@pytest.mark.django_db
def test_latest_message_ignores_deleted():
    srv = DiscordServer.objects.create(server_id=_uid(), server_name="G", icon_url="")
    ch = DiscordChannel.objects.create(
        server=srv, channel_id=_uid(), channel_name="c", channel_type="text"
    )
    author = DiscordProfile.objects.create(
        discord_user_id=_uid(),
        username="u",
        display_name="U",
        avatar_url="",
        is_bot=False,
    )
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    DiscordMessage.objects.create(
        message_id=_uid(),
        channel=ch,
        author=author,
        content="deleted",
        message_created_at=t,
        is_deleted=True,
    )
    assert latest_message_created_at_for_guild(srv.server_id, channel_ids=None) is None


@pytest.mark.django_db
def test_latest_message_respects_channel_allowlist():
    srv = DiscordServer.objects.create(server_id=_uid(), server_name="G", icon_url="")
    ch1 = DiscordChannel.objects.create(
        server=srv, channel_id=_uid(), channel_name="a", channel_type="text"
    )
    ch2 = DiscordChannel.objects.create(
        server=srv, channel_id=_uid(), channel_name="b", channel_type="text"
    )
    author = DiscordProfile.objects.create(
        discord_user_id=_uid(),
        username="u",
        display_name="U",
        avatar_url="",
        is_bot=False,
    )
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    DiscordMessage.objects.create(
        message_id=_uid(),
        channel=ch1,
        author=author,
        content="older",
        message_created_at=t1,
    )
    DiscordMessage.objects.create(
        message_id=_uid(),
        channel=ch2,
        author=author,
        content="newer",
        message_created_at=t2,
    )
    latest = latest_message_created_at_for_guild(
        srv.server_id, channel_ids=[ch1.channel_id]
    )
    assert latest == t1


def test_utc_day_start_normalizes_to_midnight():
    dt = datetime(2026, 6, 2, 22, 30, 45, tzinfo=timezone.utc)
    assert utc_day_start(dt) == datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc)


def test_iter_channel_export_days_empty_after_is_today_only():
    now = datetime(2026, 6, 11, 15, 0, 0, tzinfo=timezone.utc)
    days = iter_channel_export_days(after=None, before=None, now=now)
    assert len(days) == 1
    assert days[0][0] == "2026-06-11"
    assert days[0][1] == datetime(2026, 6, 11, 0, 0, 0, tzinfo=timezone.utc)
    assert days[0][2] == now


def test_iter_channel_export_days_spans_multiple_days():
    after = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    before = datetime(2026, 6, 3, 8, 0, 0, tzinfo=timezone.utc)
    days = iter_channel_export_days(after=after, before=before, now=before)
    assert [d[0] for d in days] == ["2026-06-01", "2026-06-02", "2026-06-03"]
    assert days[0][1] == after
    assert days[-1][2] == before


@pytest.mark.django_db
def test_latest_message_per_channel():
    srv = DiscordServer.objects.create(server_id=_uid(), server_name="G", icon_url="")
    ch1 = DiscordChannel.objects.create(
        server=srv, channel_id=_uid(), channel_name="a", channel_type="text"
    )
    ch2 = DiscordChannel.objects.create(
        server=srv, channel_id=_uid(), channel_name="b", channel_type="text"
    )
    author = DiscordProfile.objects.create(
        discord_user_id=_uid(),
        username="u",
        display_name="U",
        avatar_url="",
        is_bot=False,
    )
    t1 = datetime(2026, 4, 1, 15, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
    DiscordMessage.objects.create(
        message_id=_uid(),
        channel=ch1,
        author=author,
        content="a",
        message_created_at=t1,
    )
    DiscordMessage.objects.create(
        message_id=_uid(),
        channel=ch2,
        author=author,
        content="b",
        message_created_at=t2,
    )
    assert latest_message_created_at_for_channel(srv.server_id, ch1.channel_id) == t1
    assert latest_message_created_at_for_channel(srv.server_id, ch2.channel_id) == t2


def test_incremental_export_after_floors_to_utc_day_start():
    latest = datetime(2026, 6, 10, 22, 45, 0, tzinfo=timezone.utc)
    assert incremental_export_after(latest) == datetime(
        2026, 6, 10, 0, 0, 0, tzinfo=timezone.utc
    )


@pytest.mark.django_db
def test_resolve_channel_export_after_uses_day_start_without_explicit_since():
    srv = DiscordServer.objects.create(server_id=_uid(), server_name="G", icon_url="")
    ch = DiscordChannel.objects.create(
        server=srv, channel_id=_uid(), channel_name="c", channel_type="text"
    )
    author = DiscordProfile.objects.create(
        discord_user_id=_uid(),
        username="u",
        display_name="U",
        avatar_url="",
        is_bot=False,
    )
    latest = datetime(2026, 6, 10, 18, 0, 0, tzinfo=timezone.utc)
    DiscordMessage.objects.create(
        message_id=_uid(),
        channel=ch,
        author=author,
        content="msg",
        message_created_at=latest,
    )
    resolved = resolve_channel_export_after(
        srv.server_id,
        ch.channel_id,
        explicit_after=None,
    )
    assert resolved == datetime(2026, 6, 10, 0, 0, 0, tzinfo=timezone.utc)


def test_resolve_channel_export_after_honors_explicit_since():
    explicit = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert resolve_channel_export_after(1, 2, explicit_after=explicit) == explicit


def test_iter_channel_export_days_naive_before_treated_as_utc():
    after = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    before_naive = datetime(2026, 6, 3, 8, 0, 0)
    before_aware = datetime(2026, 6, 3, 8, 0, 0, tzinfo=timezone.utc)
    naive_days = iter_channel_export_days(
        after=after, before=before_naive, now=before_aware
    )
    aware_days = iter_channel_export_days(
        after=after, before=before_aware, now=before_aware
    )
    assert naive_days == aware_days
    assert [d[0] for d in naive_days] == ["2026-06-01", "2026-06-02", "2026-06-03"]


def test_iter_channel_export_days_clips_partial_last_day():
    after = datetime(2026, 6, 2, 22, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 6, 2, 23, 30, 0, tzinfo=timezone.utc)
    days = iter_channel_export_days(after=after, before=None, now=now)
    assert len(days) == 1
    assert days[0][0] == "2026-06-02"
    assert days[0][1] == after
    assert days[0][2] == now
