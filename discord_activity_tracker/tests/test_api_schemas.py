"""Tests for discord_activity_tracker.api_schemas."""

from datetime import datetime, timezone

import pytest

from discord_activity_tracker.api_schemas import (
    DiscordLiveSyncValidationError,
    parse_live_message,
    parse_live_user,
    parse_reaction,
)
from discord_activity_tracker.services import bulk_upsert_discord_users
from discord_activity_tracker.sync.utils import parse_discord_user


def test_parse_discord_user_returns_payload():
    user = parse_discord_user(
        {
            "id": 99,
            "username": "bot",
            "display_name": "Bot",
            "avatar_url": "",
            "bot": True,
        }
    )
    assert user.user_id == 99
    assert user.is_bot is True


def test_parse_live_message():
    created = datetime(2024, 1, 1, tzinfo=timezone.utc)
    msg = parse_live_message(
        {
            "message_id": 42,
            "author": {
                "user_id": 1,
                "username": "u",
                "display_name": "",
                "avatar_url": "",
                "is_bot": False,
            },
            "message_created_at": created,
            "content": "hello",
        }
    )
    assert msg.message_id == 42
    assert msg.author.user_id == 1


def test_parse_live_message_missing_id_raises():
    with pytest.raises(DiscordLiveSyncValidationError):
        parse_live_message(
            {
                "author": {"user_id": 1, "username": "u"},
                "message_created_at": datetime.now(timezone.utc),
            }
        )


def test_parse_reaction():
    r = parse_reaction({"discord_message_id": 1, "emoji": "thumbsup", "count": 2})
    assert r.emoji == "thumbsup"


@pytest.mark.django_db
def test_bulk_upsert_discord_users_no_keyerror_on_typed_payload():
    users = bulk_upsert_discord_users(
        [
            parse_live_user(
                {
                    "user_id": 900001,
                    "username": "typed",
                    "display_name": "",
                    "avatar_url": "",
                    "is_bot": False,
                }
            )
        ]
    )
    assert 900001 in users
