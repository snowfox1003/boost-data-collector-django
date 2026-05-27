"""Tests for slack_event_handler.utils.slack_tokens (no real Chrome profile)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from slack_event_handler.utils import slack_tokens as st


@pytest.fixture
def sample_local_config():
    return {
        "teams": {
            "T1": {"token": "xoxc-1", "name": "Team One", "user_id": "U1"},
            "T2": {"token": "xoxc-2", "name": "Team Two", "user_id": "U2"},
        }
    }


def test_is_slack_internal_token_auth_error():
    assert st.is_slack_internal_token_auth_error("invalid_auth")
    assert not st.is_slack_internal_token_auth_error("file_not_found")


@patch("slack_event_handler.utils.slack_tokens.requests.post")
def test_probe_slack_internal_tokens_ok(mock_post):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"ok": False, "error": "file_not_found"}
    mock_post.return_value = mock_resp
    assert st.probe_slack_internal_tokens("xc", "xd") is True


@patch("slack_event_handler.utils.slack_tokens.requests.post")
def test_probe_slack_internal_tokens_auth_error(mock_post):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"ok": False, "error": "invalid_auth"}
    mock_post.return_value = mock_resp
    assert st.probe_slack_internal_tokens("xc", "xd") is False


def test_probe_slack_internal_tokens_empty():
    assert st.probe_slack_internal_tokens("", "xd") is False


@override_settings(CHROME_PROFILE_PATH="", WORKSPACE_DIR="/tmp/ws")
def test_resolve_chrome_profile_uses_workspace_default(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    expected = tmp_path / "slack_event_handler" / "chrome_profile"
    expected.mkdir(parents=True)
    assert st._resolve_chrome_profile_root() == expected.resolve()


def test_resolve_chrome_profile_respects_custom_path(tmp_path):
    custom = tmp_path / "custom_slack_chrome"
    custom.mkdir()
    with override_settings(CHROME_PROFILE_PATH=str(custom), WORKSPACE_DIR="/tmp/ws"):
        assert st._resolve_chrome_profile_root() == custom.resolve()


def test_validate_chrome_profile_path_ok():
    assert "/home/user/profile" in st._validate_chrome_profile_path(
        "/home/user/profile"
    )


@pytest.mark.parametrize("bad", ["", None, "bad\x00path", "???"])
def test_validate_chrome_profile_path_bad(bad):
    with pytest.raises(ValueError):
        st._validate_chrome_profile_path(bad)


def test_parse_local_config_raw_strips_prefix_byte():
    payload = {"teams": {}}
    raw = b"\x01" + json.dumps(payload).encode("utf-8")
    assert st._parse_local_config_raw(raw) == payload


def test_extract_slack_tokens_from_config_success(sample_local_config):
    out = st.extract_slack_tokens_from_config(sample_local_config, "xoxd-val", "T1")
    assert out["xoxc"] == "xoxc-1"
    assert out["xoxd"] == "xoxd-val"
    assert out["team_id"] == "T1"
    assert out["team_name"] == "Team One"


def test_extract_slack_tokens_from_config_missing_team(sample_local_config):
    assert st.extract_slack_tokens_from_config(sample_local_config, "d", "TX") is None


def test_extract_slack_tokens_from_config_missing_xoxd(sample_local_config):
    assert st.extract_slack_tokens_from_config(sample_local_config, "", "T1") is None


def test_get_all_team_ids_from_config(sample_local_config):
    assert set(st.get_all_team_ids_from_config(sample_local_config)) == {"T1", "T2"}


def test_get_all_team_ids_with_explicit_config(sample_local_config):
    assert st.get_all_team_ids(sample_local_config) == ["T1", "T2"]


@patch.object(st, "_read_local_config_v2", return_value=None)
@patch.object(st, "_resolve_chrome_profile_root", return_value=Path("/tmp/profile"))
def test_get_all_team_ids_empty_when_no_config(_resolve, _read):
    assert st.get_all_team_ids() == []


def test_read_local_config_v2_parses_leveldb(tmp_path):
    profile = tmp_path / "chrome_profile"
    leveldb_dir = profile / "Default" / "Local Storage" / "leveldb"
    leveldb_dir.mkdir(parents=True)
    config = {"teams": {"T1": {"token": "x"}}}

    with patch.object(
        st, "_read_leveldb_value", return_value=b"\x01" + json.dumps(config).encode()
    ):
        out = st._read_local_config_v2(profile)
    assert out == config


def test_read_local_config_v2_returns_none_when_no_leveldb(tmp_path):
    profile = tmp_path / "empty_profile"
    profile.mkdir()
    assert st._read_local_config_v2(profile) is None


@patch("browser_cookie3.chrome")
def test_read_xoxd_cookie_success(mock_chrome, tmp_path):
    profile = tmp_path / "profile"
    cookies = profile / "Default" / "Cookies"
    cookies.parent.mkdir(parents=True)
    cookies.touch()
    cookie = MagicMock()
    cookie.name = "d"
    cookie.value = "xoxd-abc"
    mock_chrome.return_value = [cookie]
    assert st._read_xoxd_cookie(profile) == "xoxd-abc"


@patch("browser_cookie3.chrome")
def test_read_xoxd_cookie_missing(mock_chrome, tmp_path):
    profile = tmp_path / "profile"
    cookies = profile / "Default" / "Cookies"
    cookies.parent.mkdir(parents=True)
    cookies.touch()
    mock_chrome.return_value = []
    assert st._read_xoxd_cookie(profile) is None


def test_decrypt_chrome_linux_v10_cookie_roundtrip():
    from Cryptodome.Cipher import AES

    value = "xoxd-test-token"
    padded = value.encode("utf-8")
    pad_len = 16 - (len(padded) % 16)
    padded += bytes([pad_len]) * pad_len
    payload = b"x" * 32 + padded
    cipher = AES.new(st._chrome_linux_v10_cookie_key(), AES.MODE_CBC, iv=b" " * 16)
    encrypted = b"v10" + cipher.encrypt(payload)
    assert st._decrypt_chrome_linux_v10_cookie(encrypted) == value


@patch("browser_cookie3.chrome", side_effect=ValueError("dbus"))
def test_read_xoxd_cookie_sqlite_fallback(mock_chrome, tmp_path):
    from Cryptodome.Cipher import AES

    profile = tmp_path / "profile"
    cookies = profile / "Default" / "Cookies"
    cookies.parent.mkdir(parents=True)
    value = "xoxd-from-sqlite"
    padded = value.encode("utf-8")
    pad_len = 16 - (len(padded) % 16)
    padded += bytes([pad_len]) * pad_len
    payload = b"x" * 32 + padded
    cipher = AES.new(st._chrome_linux_v10_cookie_key(), AES.MODE_CBC, iv=b" " * 16)
    encrypted = b"v10" + cipher.encrypt(payload)

    import sqlite3

    conn = sqlite3.connect(cookies)
    conn.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB)"
    )
    conn.execute(
        "INSERT INTO cookies VALUES (?, ?, ?)",
        (".slack.com", "d", encrypted),
    )
    conn.commit()
    conn.close()

    assert st._read_xoxd_cookie(profile) == value


@patch.object(st, "_read_xoxd_cookie", return_value="xoxd")
@patch.object(st, "_read_local_config_v2")
@patch.object(st, "_resolve_chrome_profile_root")
def test_extract_slack_tokens_auto_success(
    mock_resolve, mock_config, mock_cookie, sample_local_config, tmp_path, settings
):
    profile = tmp_path / "profile"
    profile.mkdir()
    settings.CHROME_PROFILE_PATH = str(profile)
    mock_resolve.return_value = profile
    mock_config.return_value = sample_local_config
    out = st.extract_slack_tokens_auto("T1")
    assert out["xoxc"] == "xoxc-1"
    assert out["xoxd"] == "xoxd"


@patch.object(st, "_resolve_chrome_profile_root")
def test_extract_slack_tokens_auto_missing_profile(mock_resolve, settings):
    settings.CHROME_PROFILE_PATH = "/nonexistent/profile/path"
    mock_resolve.return_value = Path("/nonexistent/profile/path")
    assert st.extract_slack_tokens_auto("T1") is None


@patch.object(st, "_read_xoxd_cookie", return_value=None)
@patch.object(st, "_read_local_config_v2", return_value={"teams": {}})
@patch.object(st, "_resolve_chrome_profile_root")
def test_extract_slack_tokens_auto_no_cookie(
    mock_resolve, mock_config, mock_cookie, tmp_path, settings
):
    profile = tmp_path / "profile"
    profile.mkdir()
    settings.CHROME_PROFILE_PATH = str(profile)
    mock_resolve.return_value = profile
    assert st.extract_slack_tokens_auto("T1") is None
