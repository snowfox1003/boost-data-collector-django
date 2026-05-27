"""Tests for cppa_slack_tracker.api_schemas."""

import pytest

from cppa_slack_tracker.api_schemas import (
    SlackApiValidationError,
    parse_channel,
    parse_message,
    parse_team,
    parse_user,
)


def test_parse_team_from_api_shape():
    team = parse_team({"id": "T1", "name": "Workspace"})
    assert team.team_id == "T1"
    assert team.team_name == "Workspace"


def test_parse_team_internal_shape():
    team = parse_team({"team_id": "T2", "team_name": "Other"})
    assert team.team_id == "T2"


def test_parse_team_missing_id_raises():
    with pytest.raises(SlackApiValidationError):
        parse_team({"name": "x"})


def test_parse_channel():
    ch = parse_channel(
        {
            "id": "C1",
            "name": "general",
            "is_channel": True,
            "is_private": False,
        }
    )
    assert ch.id == "C1"


def test_parse_user():
    user = parse_user(
        {
            "id": "U1",
            "name": "alice",
            "real_name": "Alice",
            "profile": {"email": "a@example.com"},
        }
    )
    assert user.id == "U1"


def test_parse_user_non_dict_raises():
    with pytest.raises(SlackApiValidationError, match="expected object"):
        parse_user("not-a-user")  # type: ignore[arg-type]


def test_parse_message():
    msg = parse_message({"ts": "1.0", "user": "U1", "text": "hi"})
    assert msg.ts == "1.0"
