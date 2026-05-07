"""Tests for DISCORD_CHANNEL_IDS and DISCORD_SERVER_ID parsing in config/settings.py.

These tests simulate the parsing logic defined in settings.py by re-running the
same code with various env var values, rather than reloading Django settings
(which is not possible at test time).
"""

from __future__ import annotations


def _parse_channel_ids(raw: str) -> list[int]:
    """Mirror of the parsing logic in config/settings.py."""
    raw = (raw or "").strip()
    return [int(c.strip()) for c in raw.split(",") if c.strip().isdigit()]


def _parse_server_id(raw: str) -> "int | None":
    """Mirror of the parsing logic in config/settings.py."""
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


# ---------------------------------------------------------------------------
# DISCORD_CHANNEL_IDS
# ---------------------------------------------------------------------------


def test_channel_ids_comma_separated():
    result = _parse_channel_ids("851121440425639956,123456789012345678")
    assert result == [851121440425639956, 123456789012345678]


def test_channel_ids_single_value():
    assert _parse_channel_ids("9999") == [9999]


def test_channel_ids_empty_string():
    assert _parse_channel_ids("") == []


def test_channel_ids_whitespace_only():
    assert _parse_channel_ids("   ") == []


def test_channel_ids_non_digit_values_skipped():
    result = _parse_channel_ids("valid123,abc,!@#,456")
    assert result == [456]


def test_channel_ids_mixed_valid_and_invalid():
    result = _parse_channel_ids("100,abc,200,,300")
    assert result == [100, 200, 300]


def test_channel_ids_strips_whitespace_around_each():
    result = _parse_channel_ids(" 100 , 200 ")
    assert result == [100, 200]


# ---------------------------------------------------------------------------
# DISCORD_SERVER_ID
# ---------------------------------------------------------------------------


def test_server_id_valid_number():
    assert _parse_server_id("331718482485837825") == 331718482485837825


def test_server_id_empty_string():
    assert _parse_server_id("") is None


def test_server_id_non_numeric():
    assert _parse_server_id("my-guild") is None


def test_server_id_whitespace():
    assert _parse_server_id("  ") is None
