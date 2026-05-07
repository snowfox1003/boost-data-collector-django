"""Coverage for Discord model __str__ methods."""

import pytest

from cppa_user_tracker.models import DiscordProfile
from discord_activity_tracker.models import (
    DiscordChannel,
    DiscordMessage,
    DiscordReaction,
    DiscordServer,
)


@pytest.mark.django_db
def test_discord_server_str():
    s = DiscordServer.objects.create(server_id=1, server_name="Guild", icon_url="")
    assert "Guild" in str(s) and "1" in str(s)


@pytest.mark.django_db
def test_discord_channel_str():
    s = DiscordServer.objects.create(server_id=2, server_name="G", icon_url="")
    ch = DiscordChannel.objects.create(
        server=s,
        channel_id=3,
        channel_name="help",
        channel_type="text",
    )
    assert "#help" == str(ch)


@pytest.mark.django_db
def test_discord_channel_str_with_category():
    """Category fields are stored correctly; channel str is still the name."""
    s = DiscordServer.objects.create(server_id=20, server_name="G", icon_url="")
    ch = DiscordChannel.objects.create(
        server=s,
        channel_id=30,
        channel_name="c-cpp-discussion",
        channel_type="GuildTextChat",
        category_id=855220194887335977,
        category_name="Discussion",
    )
    assert "#c-cpp-discussion" == str(ch)
    ch.refresh_from_db()
    assert ch.category_id == 855220194887335977
    assert ch.category_name == "Discussion"


@pytest.mark.django_db
def test_discord_message_and_reaction_str():
    s = DiscordServer.objects.create(server_id=4, server_name="G", icon_url="")
    ch = DiscordChannel.objects.create(
        server=s,
        channel_id=5,
        channel_name="c",
        channel_type="text",
    )
    author = DiscordProfile.objects.create(
        discord_user_id=99,
        username="alice",
        display_name="Alice",
        avatar_url="",
        is_bot=False,
    )
    from django.utils import timezone as dj_tz

    msg = DiscordMessage.objects.create(
        message_id=100,
        channel=ch,
        author=author,
        content="hello world example text",
        message_created_at=dj_tz.now(),
    )
    assert "alice" in str(msg)
    assert "hello" in str(msg)

    r = DiscordReaction.objects.create(message=msg, emoji="👍", count=2)
    assert "👍" in str(r) and "2" in str(r)


@pytest.mark.django_db
def test_discord_message_type_and_is_pinned_fields():
    """New message_type and is_pinned fields persist correctly."""
    from django.utils import timezone as dj_tz

    s = DiscordServer.objects.create(server_id=40, server_name="G", icon_url="")
    ch = DiscordChannel.objects.create(
        server=s,
        channel_id=50,
        channel_name="announcements",
        channel_type="GuildTextChat",
    )
    author = DiscordProfile.objects.create(
        discord_user_id=990,
        username="bob",
        display_name="Bob",
        avatar_url="",
        is_bot=False,
    )
    msg = DiscordMessage.objects.create(
        message_id=200,
        channel=ch,
        author=author,
        content="pinned reply",
        message_type="Reply",
        is_pinned=True,
        message_created_at=dj_tz.now(),
    )
    msg.refresh_from_db()
    assert msg.message_type == "Reply"
    assert msg.is_pinned is True
