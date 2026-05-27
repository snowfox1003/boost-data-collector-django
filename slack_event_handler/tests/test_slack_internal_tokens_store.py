"""Tests for workspace JSON Slack internal token storage."""

import json
from unittest.mock import patch

import pytest
from django.test import override_settings

from slack_event_handler.utils import slack_internal_tokens_store as store


@override_settings(
    WORKSPACE_DIR="/tmp/ws",
    SLACK_INTERNAL_TOKENS_JSON="",
)
def test_save_and_load_tokens(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    path = store.save_slack_internal_tokens(
        "T1", "xoxc-abc", "xoxd-xyz", team_name="Team"
    )
    assert path == tmp_path / "slack_event_handler" / "slack_internal_tokens.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["teams"]["T1"]["xoxc"] == "xoxc-abc"
    assert data["teams"]["T1"]["xoxd"] == "xoxd-xyz"
    loaded = store.load_slack_internal_tokens("T1")
    assert loaded["xoxc"] == "xoxc-abc"
    assert loaded["team_name"] == "Team"


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
def test_get_slack_internal_token_pair(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_slack_internal_tokens("T1", "xc", "xd")
    with override_settings(SLACK_TEAM_IDS="T1"):
        pair = store.get_slack_internal_token_pair("T1")
    assert pair == ("xc", "xd")


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=False, WORKSPACE_DIR="/tmp/ws")
def test_get_pair_disabled(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_slack_internal_tokens("T1", "xc", "xd")
    assert store.get_slack_internal_token_pair("T1") is None


def test_save_requires_fields():
    with pytest.raises(ValueError):
        store.save_slack_internal_tokens("", "a", "b")


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "slack_event_handler.utils.slack_tokens.probe_slack_internal_tokens",
    return_value=True,
)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.extract_and_save_slack_internal_tokens",
    return_value=("xc", "xd"),
)
def test_get_or_load_extracts_when_json_missing(
    mock_extract, _mock_probe, tmp_path, settings
):
    settings.WORKSPACE_DIR = str(tmp_path)
    pair = store.get_or_load_slack_internal_token_pair("T1")
    assert pair == ("xc", "xd")
    mock_extract.assert_called_once_with("T1")


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "slack_event_handler.utils.slack_tokens.probe_slack_internal_tokens",
    side_effect=[False, True],
)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.extract_and_save_slack_internal_tokens",
    return_value=("new-xc", "new-xd"),
)
def test_get_or_load_reextracts_when_json_tokens_stale(
    mock_extract, _mock_probe, tmp_path, settings
):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_slack_internal_tokens("T1", "old-xc", "old-xd")
    pair = store.get_or_load_slack_internal_token_pair("T1")
    assert pair == ("new-xc", "new-xd")
    mock_extract.assert_called_once_with("T1")


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "slack_event_handler.utils.slack_tokens.probe_slack_internal_tokens",
    return_value=False,
)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.extract_and_save_slack_internal_tokens",
    return_value=("bad-xc", "bad-xd"),
)
def test_get_or_load_logs_when_reextracted_tokens_still_invalid(
    mock_extract, _mock_probe, tmp_path, settings, caplog
):
    import logging

    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_slack_internal_tokens("T1", "old-xc", "old-xd")
    with caplog.at_level(logging.ERROR):
        pair = store.get_or_load_slack_internal_token_pair("T1")
    assert pair is None
    mock_extract.assert_called_once_with("T1")
    assert "still invalid" in caplog.text
    assert "slack-tokens-refresh" in caplog.text


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "slack_event_handler.utils.slack_tokens.probe_slack_internal_tokens",
    return_value=True,
)
def test_get_or_load_keeps_valid_json_tokens(_mock_probe, tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    store.save_slack_internal_tokens("T1", "xc", "xd")
    pair = store.get_or_load_slack_internal_token_pair("T1")
    assert pair == ("xc", "xd")
    _mock_probe.assert_called_once_with("xc", "xd")
