"""Tests for discord_activity_tracker.sync.utils."""

from discord_activity_tracker.sync.utils import (
    format_discord_url,
    parse_datetime,
    parse_discord_user,
    sanitize_channel_name,
    truncate_content,
)


def test_parse_datetime_empty():
    assert parse_datetime("") is None
    assert parse_datetime(None) is None


def test_parse_datetime_z_normalized():
    dt = parse_datetime("2026-03-01T15:30:00Z")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_datetime_invalid_returns_none():
    assert parse_datetime("not-a-timestamp") is None


def test_parse_discord_user_empty_dict():
    out = parse_discord_user(None)
    assert out["user_id"] == 0
    assert out["username"] == "unknown"
    assert out["is_bot"] is False


def test_parse_discord_user_bot_api_shape():
    out = parse_discord_user(
        {
            "id": 123456789012345678,
            "username": "alice",
            "display_name": "Alice",
            "avatar_url": "https://cdn.example/a.png",
            "bot": True,
        }
    )
    assert out["user_id"] == 123456789012345678
    assert out["username"] == "alice"
    assert out["display_name"] == "Alice"
    assert out["avatar_url"] == "https://cdn.example/a.png"
    assert out["is_bot"] is True


def test_parse_discord_user_exporter_name_fallback():
    out = parse_discord_user({"id": 1, "name": "bob"})
    assert out["username"] == "bob"


# --- new: DiscordChatExporter shape ---


def test_parse_discord_user_string_id_coerced_to_int():
    """Exporter provides id as string; must become int."""
    out = parse_discord_user({"id": "1082347485026070548", "name": "raubtier"})
    assert out["user_id"] == 1082347485026070548
    assert isinstance(out["user_id"], int)


def test_parse_discord_user_avatarUrl_camelCase():
    """Exporter uses camelCase avatarUrl; parse_discord_user should pick it up."""
    out = parse_discord_user(
        {
            "id": "99",
            "name": "Raubtier-Asyl",
            "avatarUrl": "https://cdn.discordapp.com/avatar.png",
        }
    )
    assert out["avatar_url"] == "https://cdn.discordapp.com/avatar.png"


def test_parse_discord_user_avatar_url_takes_priority_over_avatarUrl():
    """When both keys exist, avatar_url (Bot API key) wins."""
    out = parse_discord_user(
        {
            "id": "1",
            "name": "x",
            "avatar_url": "https://cdn/a",
            "avatarUrl": "https://cdn/b",
        }
    )
    assert out["avatar_url"] == "https://cdn/a"


def test_parse_discord_user_isBot_camelCase():
    """Exporter uses isBot; must be interpreted as a boolean."""
    out = parse_discord_user({"id": "1", "name": "mybot", "isBot": True})
    assert out["is_bot"] is True


def test_parse_discord_user_nickname_as_display_name():
    """Exporter uses nickname; should be captured in display_name."""
    out = parse_discord_user(
        {
            "id": "5",
            "name": "user5",
            "nickname": "Cool User",
        }
    )
    assert out["display_name"] == "Cool User"


def test_parse_discord_user_invalid_id_defaults_to_zero():
    out = parse_discord_user({"id": "not-a-number", "name": "x"})
    assert out["user_id"] == 0


def test_parse_discord_user_none_id_defaults_to_zero():
    out = parse_discord_user({"id": None, "name": "x"})
    assert out["user_id"] == 0


# --- unchanged helpers ---


def test_sanitize_channel_name_strips_unsafe_chars():
    assert "/" not in sanitize_channel_name("a/b")
    assert "*" not in sanitize_channel_name("x*y")
    assert "?" not in sanitize_channel_name("help?")


def test_format_discord_url():
    assert format_discord_url(1, 2, 3) == "https://discord.com/channels/1/2/3"


def test_truncate_content_short_unchanged():
    assert truncate_content("hi", max_length=100) == "hi"


def test_truncate_content_long_adds_ellipsis():
    s = "x" * 50
    out = truncate_content(s, max_length=10)
    assert out.endswith("...")
    assert len(out) == 10
