"""Tests for Slack-related settings helpers in config.settings."""

import pytest

from config.settings import (
    _slack_per_team_tokens_from_env,
    _slack_team_ids_from_env,
    _slack_team_scope_from_env,
)


@pytest.fixture(autouse=True)
def _clear_slack_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("SLACK_"):
            monkeypatch.delenv(key, raising=False)


def test_slack_team_ids_from_env_empty(monkeypatch):
    monkeypatch.delenv("SLACK_TEAM_IDS", raising=False)
    assert _slack_team_ids_from_env() == []


def test_slack_team_ids_from_env_parses_comma_separated(monkeypatch):
    monkeypatch.setenv("SLACK_TEAM_IDS", " T1 , T2, ,T3 ")
    assert _slack_team_ids_from_env() == ["T1", "T2", "T3"]


def test_slack_per_team_tokens_from_env(monkeypatch):
    monkeypatch.setenv("SLACK_TEAM_IDS", "T1,T2")
    monkeypatch.setenv("SLACK_BOT_TOKEN_T1", "xoxb-one")
    monkeypatch.setenv("SLACK_BOT_TOKEN_T2", "")
    assert _slack_per_team_tokens_from_env("SLACK_BOT_TOKEN") == {"T1": "xoxb-one"}


def test_slack_team_scope_defaults_when_missing(monkeypatch):
    monkeypatch.setenv("SLACK_TEAM_IDS", "T1")
    assert _slack_team_scope_from_env() == {"T1": [0, 1]}


def test_slack_team_scope_parses_valid_entries(monkeypatch):
    monkeypatch.setenv("SLACK_TEAM_IDS", "T1")
    monkeypatch.setenv("SLACK_TEAM_SCOPE_T1", "0, 1")
    assert _slack_team_scope_from_env() == {"T1": [0, 1]}


def test_slack_team_scope_skips_invalid_and_defaults(monkeypatch):
    monkeypatch.setenv("SLACK_TEAM_IDS", "T1")
    monkeypatch.setenv("SLACK_TEAM_SCOPE_T1", "99, bogus, 1")
    assert _slack_team_scope_from_env() == {"T1": [1]}


def test_slack_team_scope_all_invalid_falls_back_to_both(monkeypatch):
    monkeypatch.setenv("SLACK_TEAM_IDS", "T1")
    monkeypatch.setenv("SLACK_TEAM_SCOPE_T1", "99, abc")
    assert _slack_team_scope_from_env() == {"T1": [0, 1]}
