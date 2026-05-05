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
    assert out["is_bot"] is True


def test_parse_discord_user_exporter_name_fallback():
    out = parse_discord_user({"id": 1, "name": "bob"})
    assert out["username"] == "bob"


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
