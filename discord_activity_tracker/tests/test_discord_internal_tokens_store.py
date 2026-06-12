"""Tests for workspace JSON Discord internal token storage."""

import json
import logging
from unittest.mock import patch

import pytest
from django.test import override_settings

from discord_activity_tracker.utils import discord_internal_tokens_store as store


@override_settings(
    WORKSPACE_DIR="/tmp/ws",
    DISCORD_INTERNAL_TOKENS_JSON="",
)
def test_save_and_load_tokens(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    path = store.save_discord_internal_tokens(
        "discord-tok", user_id="123", username="alice"
    )
    assert (
        path == tmp_path / "discord_activity_tracker" / "discord_internal_tokens.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["user_token"] == "discord-tok"
    assert data["user_id"] == "123"
    loaded = store.load_discord_internal_tokens()
    assert loaded["user_token"] == "discord-tok"
    assert loaded["username"] == "alice"


@override_settings(ALLOW_INTERNAL_DISCORD_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
def test_get_discord_user_token_from_json(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_discord_internal_tokens("tok")
    assert store.get_discord_user_token_from_json() == "tok"


@override_settings(ALLOW_INTERNAL_DISCORD_TOKENS=False, WORKSPACE_DIR="/tmp/ws")
def test_get_token_from_json_disabled(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_discord_internal_tokens("tok")
    assert store.get_discord_user_token_from_json() is None


def test_save_requires_token():
    with pytest.raises(ValueError):
        store.save_discord_internal_tokens("")


@override_settings(ALLOW_INTERNAL_DISCORD_TOKENS=False, DISCORD_USER_TOKEN="env-tok")
def test_get_or_load_uses_env_when_internal_disabled():
    assert store.get_or_load_discord_user_token() == "env-tok"


@override_settings(ALLOW_INTERNAL_DISCORD_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "discord_activity_tracker.utils.discord_tokens.probe_discord_user_token",
    return_value=True,
)
@patch(
    "discord_activity_tracker.utils.discord_internal_tokens_store.extract_and_save_discord_internal_tokens",
    return_value="fresh-tok",
)
def test_get_or_load_extracts_when_json_missing(
    mock_extract, _mock_probe, tmp_path, settings
):
    settings.WORKSPACE_DIR = str(tmp_path)
    token = store.get_or_load_discord_user_token()
    assert token == "fresh-tok"
    mock_extract.assert_called_once()


@override_settings(ALLOW_INTERNAL_DISCORD_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "discord_activity_tracker.utils.discord_tokens.probe_discord_user_token",
    side_effect=[False, True],
)
@patch(
    "discord_activity_tracker.utils.discord_internal_tokens_store.extract_and_save_discord_internal_tokens",
    return_value="new-tok",
)
def test_get_or_load_reextracts_when_json_tokens_stale(
    mock_extract, _mock_probe, tmp_path, settings
):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_discord_internal_tokens("old-tok")
    token = store.get_or_load_discord_user_token()
    assert token == "new-tok"
    mock_extract.assert_called_once()


@override_settings(ALLOW_INTERNAL_DISCORD_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "discord_activity_tracker.utils.discord_tokens.probe_discord_user_token",
    return_value=False,
)
@patch(
    "discord_activity_tracker.utils.discord_internal_tokens_store.extract_and_save_discord_internal_tokens",
    return_value="bad-tok",
)
def test_get_or_load_logs_when_reextracted_tokens_still_invalid(
    mock_extract, _mock_probe, tmp_path, settings, caplog
):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_discord_internal_tokens("old-tok")
    with caplog.at_level(logging.ERROR):
        token = store.get_or_load_discord_user_token()
    assert token is None
    mock_extract.assert_called_once()
    assert "still invalid" in caplog.text
    assert ".env.example" in caplog.text


@override_settings(ALLOW_INTERNAL_DISCORD_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "discord_activity_tracker.utils.discord_tokens.probe_discord_user_token",
    return_value=True,
)
def test_get_or_load_keeps_valid_json_tokens(_mock_probe, tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_discord_internal_tokens("tok")
    token = store.get_or_load_discord_user_token()
    assert token == "tok"
    _mock_probe.assert_called_once_with("tok")
