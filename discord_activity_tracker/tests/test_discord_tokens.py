"""Tests for discord_activity_tracker.utils.discord_tokens (no real Chrome profile)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from discord_activity_tracker.utils import discord_tokens as dt


def test_parse_discord_token_raw_strips_prefix_and_quotes():
    raw = b'\x01"my-discord-token"'
    assert dt._parse_discord_token_raw(raw) == "my-discord-token"


def test_parse_discord_token_raw_plain():
    assert dt._parse_discord_token_raw(b"plain-token") == "plain-token"


def test_parse_discord_token_raw_empty_raises():
    with pytest.raises(ValueError):
        dt._parse_discord_token_raw(b"")


@patch("discord_activity_tracker.utils.discord_tokens.requests.get")
def test_probe_discord_user_token_ok(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    assert dt.probe_discord_user_token("tok") is True


@patch("discord_activity_tracker.utils.discord_tokens.requests.get")
def test_probe_discord_user_token_auth_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_get.return_value = mock_resp
    assert dt.probe_discord_user_token("tok") is False


def test_probe_discord_user_token_empty():
    assert dt.probe_discord_user_token("") is False


@patch("discord_activity_tracker.utils.discord_tokens.requests.get")
def test_probe_discord_user_token_details(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "123", "username": "alice"}
    mock_get.return_value = mock_resp
    out = dt.probe_discord_user_token_details("tok")
    assert out == {"user_id": "123", "username": "alice"}


def test_is_discord_exporter_auth_error():
    assert dt.is_discord_exporter_auth_error("HTTP 401 Unauthorized")
    assert dt.is_discord_exporter_auth_error("invalid token")
    assert not dt.is_discord_exporter_auth_error("channel not found")


@override_settings(DISCORD_CHROME_PROFILE_PATH="", WORKSPACE_DIR="/tmp/ws")
def test_resolve_discord_chrome_profile_uses_workspace_default(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    expected = tmp_path / "discord_activity_tracker" / "chrome_profile"
    expected.mkdir(parents=True)
    assert dt._resolve_discord_chrome_profile_root() == expected.resolve()


def test_resolve_discord_chrome_profile_respects_custom_path(tmp_path):
    custom = tmp_path / "custom_discord_chrome"
    custom.mkdir()
    with override_settings(
        DISCORD_CHROME_PROFILE_PATH=str(custom), WORKSPACE_DIR="/tmp/ws"
    ):
        assert dt._resolve_discord_chrome_profile_root() == custom.resolve()


@pytest.mark.parametrize("bad", ["", None, "bad\x00path", "???"])
def test_validate_chrome_profile_path_bad(bad):
    with pytest.raises(ValueError):
        dt._validate_chrome_profile_path(bad)


def test_read_discord_token_from_leveldb_parses(tmp_path):
    profile = tmp_path / "chrome_profile"
    leveldb_dir = profile / "Default" / "Local Storage" / "leveldb"
    leveldb_dir.mkdir(parents=True)
    with patch.object(
        dt,
        "_read_leveldb_value",
        return_value=b'\x01"token-from-leveldb"',
    ):
        assert dt._read_discord_token_from_leveldb(profile) == "token-from-leveldb"


def test_read_discord_token_from_leveldb_returns_none_when_no_leveldb(tmp_path):
    profile = tmp_path / "empty_profile"
    profile.mkdir()
    assert dt._read_discord_token_from_leveldb(profile) is None


def test_read_discord_token_from_leveldb_falls_back_to_legacy_key(tmp_path):
    profile = tmp_path / "chrome_profile"
    leveldb_dir = profile / "Default" / "Local Storage" / "leveldb"
    leveldb_dir.mkdir(parents=True)

    def read_side_effect(_leveldb_dir, key):
        if key == dt.DISCORD_TOKEN_KEY:
            return b'\x01""'
        return b'\x01"legacy-token"'

    with patch.object(dt, "_read_leveldb_value", side_effect=read_side_effect):
        assert dt._read_discord_token_from_leveldb(profile) == "legacy-token"


@patch.object(dt, "probe_discord_user_token", return_value=True)
@patch.object(dt, "probe_discord_user_token_details", return_value={"user_id": "1"})
@patch.object(dt, "_read_discord_token_from_leveldb", return_value="tok")
@patch.object(dt, "_resolve_discord_chrome_profile_root")
def test_extract_discord_token_auto_success(
    mock_resolve, mock_read, _mock_details, _mock_probe, tmp_path, settings
):
    profile = tmp_path / "profile"
    profile.mkdir()
    settings.DISCORD_CHROME_PROFILE_PATH = str(profile)
    mock_resolve.return_value = profile
    out = dt.extract_discord_token_auto()
    assert out["user_token"] == "tok"
    assert out["user_id"] == "1"


@patch.object(dt, "_resolve_discord_chrome_profile_root")
def test_extract_discord_token_auto_missing_profile(mock_resolve, settings):
    settings.DISCORD_CHROME_PROFILE_PATH = "/nonexistent/profile/path"
    mock_resolve.return_value = Path("/nonexistent/profile/path")
    assert dt.extract_discord_token_auto() is None


@patch.object(dt, "probe_discord_user_token", return_value=False)
@patch.object(dt, "_read_discord_token_from_leveldb", return_value="bad-tok")
@patch.object(dt, "_resolve_discord_chrome_profile_root")
def test_extract_discord_token_auto_probe_fails(
    mock_resolve, _mock_read, _mock_probe, tmp_path, settings
):
    profile = tmp_path / "profile"
    profile.mkdir()
    settings.DISCORD_CHROME_PROFILE_PATH = str(profile)
    mock_resolve.return_value = profile
    assert dt.extract_discord_token_auto() is None
