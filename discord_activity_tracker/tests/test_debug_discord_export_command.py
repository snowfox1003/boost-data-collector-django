"""Tests for debug_discord_export management command."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone as dj_tz

from cppa_user_tracker.models import DiscordProfile
from discord_activity_tracker.models import (
    DiscordChannel,
    DiscordMessage,
    DiscordServer,
)


@pytest.mark.django_db
def test_debug_export_lists_replies_when_no_message_id():
    server = DiscordServer.objects.create(server_id=1, server_name="S")
    author = DiscordProfile.objects.create(
        discord_user_id=10,
        username="alice",
        display_name="Alice",
        avatar_url="",
        is_bot=False,
    )
    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=20,
        channel_name="c",
        channel_type="text",
    )
    DiscordMessage.objects.create(
        message_id=100,
        channel=ch,
        author=author,
        content="root",
        message_created_at=dj_tz.now(),
        reply_to_message_id=None,
    )
    DiscordMessage.objects.create(
        message_id=101,
        channel=ch,
        author=author,
        content="reply",
        message_created_at=dj_tz.now(),
        reply_to_message_id=100,
    )

    out = StringIO()
    call_command("debug_discord_export", limit=5, stdout=out, verbosity=0)
    text = out.getvalue()
    assert "101" in text
    assert "reply_to=100" in text


@pytest.mark.django_db
def test_debug_export_inspect_missing_message():
    out = StringIO()
    call_command(
        "debug_discord_export",
        message_id=999999999,
        stdout=out,
        verbosity=0,
    )
    assert "not found" in out.getvalue().lower()


@pytest.mark.django_db
def test_debug_export_inspect_with_reply_target():
    server = DiscordServer.objects.create(server_id=5, server_name="Srv")
    author = DiscordProfile.objects.create(
        discord_user_id=1,
        username="u1",
        display_name="U1",
        avatar_url="",
        is_bot=False,
    )
    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=9,
        channel_name="chan",
        channel_type="text",
    )
    DiscordMessage.objects.create(
        message_id=500,
        channel=ch,
        author=author,
        content="parent text here",
        message_created_at=dj_tz.now(),
        reply_to_message_id=None,
    )
    DiscordMessage.objects.create(
        message_id=501,
        channel=ch,
        author=author,
        content="child",
        message_created_at=dj_tz.now(),
        reply_to_message_id=500,
    )

    out = StringIO()
    call_command(
        "debug_discord_export",
        message_id=501,
        stdout=out,
        verbosity=0,
    )
    text = out.getvalue()
    assert "501" in text
    assert "REPLY TO" in text
    assert "parent" in text.lower()
