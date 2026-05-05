"""Tests for non-bulk discord_activity_tracker.services helpers."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from django.utils import timezone as django_timezone

from cppa_user_tracker.models import DiscordProfile
from discord_activity_tracker.models import DiscordChannel, DiscordServer
from discord_activity_tracker.services import (
    add_or_update_reaction,
    create_or_update_discord_message,
    get_active_channels,
    get_or_create_discord_channel,
    get_or_create_discord_server,
    mark_message_deleted,
    update_channel_last_activity,
    update_channel_last_synced,
)


def _uniq_id() -> int:
    return uuid.uuid4().int % (2**50)


@pytest.fixture
def server(db):
    return DiscordServer.objects.create(
        server_id=_uniq_id(), server_name="Guild", icon_url=""
    )


@pytest.fixture
def channel(server):
    return DiscordChannel.objects.create(
        server=server,
        channel_id=_uniq_id(),
        channel_name="general",
        channel_type="text",
        topic="",
        position=0,
    )


@pytest.fixture
def author(db):
    return DiscordProfile.objects.create(
        discord_user_id=_uniq_id(),
        username="writer",
        display_name="Writer",
        avatar_url="",
        is_bot=False,
    )


@pytest.mark.django_db
def test_get_or_create_discord_server_create_and_update():
    s1, created = get_or_create_discord_server(777, "Old", icon_url="")
    assert created is True
    s2, created2 = get_or_create_discord_server(777, "NewName", icon_url="http://i")
    assert created2 is False
    s2.refresh_from_db()
    assert s2.server_name == "NewName"
    assert s2.icon_url == "http://i"


@pytest.mark.django_db
def test_get_or_create_discord_channel_updates(channel, server):
    ch, created = get_or_create_discord_channel(
        server, channel.channel_id, "general", "text", topic="", position=0
    )
    assert created is False
    ch2, created2 = get_or_create_discord_channel(
        server, channel.channel_id, "general-renamed", "forum", topic="t", position=1
    )
    assert created2 is False
    ch2.refresh_from_db()
    assert ch2.channel_name == "general-renamed"
    assert ch2.channel_type == "forum"
    assert ch2.topic == "t"
    assert ch2.position == 1


@pytest.mark.django_db
def test_create_or_update_discord_message(channel, author):
    mid = _uniq_id()
    ts = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    msg, created = create_or_update_discord_message(
        mid,
        channel,
        author,
        "hello",
        message_created_at=ts,
        attachment_urls=["http://a"],
    )
    assert created is True
    assert msg.has_attachments is True
    msg2, created2 = create_or_update_discord_message(
        mid,
        channel,
        author,
        "updated",
        message_created_at=ts,
    )
    assert created2 is False
    msg2.refresh_from_db()
    assert msg2.content == "updated"


@pytest.mark.django_db
def test_mark_message_deleted(channel, author):
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
    msg, _ = create_or_update_discord_message(
        _uniq_id(), channel, author, "x", message_created_at=ts
    )
    deleted_at = datetime(2026, 4, 2, tzinfo=timezone.utc)
    mark_message_deleted(msg, deleted_at=deleted_at)
    msg.refresh_from_db()
    assert msg.is_deleted is True
    assert msg.deleted_at == deleted_at


@pytest.mark.django_db
def test_add_or_update_reaction(channel, author):
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
    msg, _ = create_or_update_discord_message(
        _uniq_id(), channel, author, "react", message_created_at=ts
    )
    r1, c1 = add_or_update_reaction(msg, "👍", 1)
    assert c1 is True
    r2, c2 = add_or_update_reaction(msg, "👍", 5)
    assert c2 is False
    r2.refresh_from_db()
    assert r2.count == 5


@pytest.mark.django_db
def test_update_channel_last_activity_and_synced(channel):
    act = django_timezone.now()
    update_channel_last_activity(channel, act)
    channel.refresh_from_db()
    assert channel.last_activity_at == act

    sync_ts = django_timezone.now() - timedelta(hours=1)
    update_channel_last_synced(channel, sync_ts)
    channel.refresh_from_db()
    assert channel.last_synced_at == sync_ts


@pytest.mark.django_db
def test_get_active_channels_filters_by_days(channel, server):
    channel.last_activity_at = django_timezone.now()
    channel.save()
    stale = DiscordChannel.objects.create(
        server=server,
        channel_id=_uniq_id(),
        channel_name="quiet",
        channel_type="text",
        topic="",
        position=1,
        last_activity_at=django_timezone.now() - timedelta(days=60),
    )
    active = get_active_channels(server, days=30)
    ids = {c.channel_id for c in active}
    assert channel.channel_id in ids
    assert stale.channel_id not in ids
