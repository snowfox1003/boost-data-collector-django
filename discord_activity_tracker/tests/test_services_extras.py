"""Coverage for small services.py branches."""

from datetime import datetime, timezone

import pytest
from django.utils import timezone as django_timezone

from cppa_user_tracker.models import DiscordProfile
from discord_activity_tracker.models import DiscordChannel, DiscordServer
from discord_activity_tracker.services import (
    bulk_process_message_batch,
    bulk_upsert_discord_messages,
    bulk_upsert_discord_reactions,
    bulk_upsert_discord_users,
    mark_message_deleted,
    update_channel_last_synced,
)


def _uniq():
    import uuid

    return uuid.uuid4().int % (2**50)


@pytest.fixture
def channel(db):
    s = DiscordServer.objects.create(server_id=_uniq(), server_name="S", icon_url="")
    return DiscordChannel.objects.create(
        server=s,
        channel_id=_uniq(),
        channel_name="c",
        channel_type="text",
    )


@pytest.mark.django_db
def test_mark_message_deleted_default_timestamp(channel):
    author = DiscordProfile.objects.create(
        discord_user_id=_uniq(),
        username="u",
        display_name="",
        avatar_url="",
        is_bot=False,
    )
    ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    from discord_activity_tracker.services import create_or_update_discord_message

    msg, _ = create_or_update_discord_message(
        _uniq(), channel, author, "x", message_created_at=ts
    )
    before = django_timezone.now()
    mark_message_deleted(msg)
    msg.refresh_from_db()
    assert msg.is_deleted is True
    assert msg.deleted_at is not None
    assert msg.deleted_at >= before


@pytest.mark.django_db
def test_update_channel_last_synced_default_now(channel):
    update_channel_last_synced(channel)
    channel.refresh_from_db()
    assert channel.last_synced_at is not None


@pytest.mark.django_db
def test_bulk_upsert_skips_message_without_author(channel):
    """Covers bulk_upsert_discord_messages warning path when author missing."""
    now = datetime(2026, 2, 17, 12, 0, 0, tzinfo=timezone.utc)
    out = bulk_upsert_discord_messages(
        [
            {
                "message_id": _uniq(),
                "author": {"user_id": _uniq()},
                "content": "orphan",
                "message_created_at": now,
                "attachment_urls": [],
            }
        ],
        channel,
        {},
    )
    assert out == {}


@pytest.mark.django_db
def test_bulk_upsert_reactions_skips_unknown_message():
    bulk_upsert_discord_reactions(
        [{"discord_message_id": _uniq(), "emoji": "\U0001f44d", "count": 1}],
        {},
    )


@pytest.mark.django_db
def test_bulk_process_empty_returns_zero(channel):
    assert bulk_process_message_batch([], channel) == 0


def test_bulk_upsert_reactions_empty():
    bulk_upsert_discord_reactions([], {})


@pytest.mark.django_db
def test_bulk_upsert_users_updates_existing_profile_fields():
    uid = _uniq()
    DiscordProfile.objects.create(
        discord_user_id=uid,
        type="discord",
        username="old_name",
        display_name="Old",
        avatar_url="",
        is_bot=False,
    )
    bulk_upsert_discord_users(
        [
            {
                "user_id": uid,
                "username": "new_name",
                "display_name": "New",
                "avatar_url": "http://avatar.example/x.png",
                "is_bot": True,
            }
        ]
    )
    p = DiscordProfile.objects.get(discord_user_id=uid)
    assert p.username == "new_name"
    assert p.display_name == "New"
    assert "avatar.example" in p.avatar_url
    assert p.is_bot is True
