"""Tests for github_activity_tracker.sync.utils (normalize, parse_github_user, parse_datetime)."""

import pytest
from datetime import datetime, timezone

from github_activity_tracker.sync.utils import (
    normalize_issue_json,
    normalize_pr_json,
    parse_datetime,
    parse_github_user,
)


def test_parse_github_user_none():
    """parse_github_user(None) returns empty-style dict."""
    out = parse_github_user(None)
    assert out["account_id"] is None
    assert out["username"] == ""
    assert out["display_name"] == ""
    assert out["avatar_url"] == ""


def test_parse_github_user_full():
    """parse_github_user with full dict returns correct fields."""
    user = {
        "id": 42,
        "login": "joe",
        "name": "Joe Dev",
        "avatar_url": "https://example.com/avatar.png",
    }
    out = parse_github_user(user)
    assert out["account_id"] == 42
    assert out["username"] == "joe"
    assert out["display_name"] == "Joe Dev"
    assert out["avatar_url"] == "https://example.com/avatar.png"


def test_parse_github_user_partial():
    """parse_github_user with missing keys uses empty string."""
    out = parse_github_user({"id": 1})
    assert out["account_id"] == 1
    assert out["username"] == ""
    assert out["display_name"] == ""
    assert out["avatar_url"] == ""


def test_parse_datetime_none():
    """parse_datetime(None) returns None."""
    assert parse_datetime(None) is None


def test_parse_datetime_empty():
    """parse_datetime('') returns None."""
    assert parse_datetime("") is None


def test_parse_datetime_iso():
    """parse_datetime parses ISO format with Z and returns timezone-aware UTC."""
    result = parse_datetime("2024-01-15T10:30:00Z")
    assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


def test_parse_datetime_invalid_returns_none():
    """parse_datetime with invalid string returns None."""
    assert parse_datetime("not-a-date") is None


@pytest.mark.parametrize(
    "date_str,expected_year",
    [
        ("2023-06-01T00:00:00Z", 2023),
        ("2025-12-31T23:59:59Z", 2025),
    ],
)
def test_parse_datetime_parametrized(date_str, expected_year):
    """Parametrized: parse_datetime returns correct year."""
    result = parse_datetime(date_str)
    assert result is not None
    assert result.year == expected_year


def test_normalize_issue_json_non_dict_issue_info():
    out = normalize_issue_json({"issue_info": "bad", "number": 1})
    assert out["issue_info"] == "bad"


def test_normalize_pr_json_non_dict_pr_info():
    out = normalize_pr_json({"pr_info": None, "number": 2})
    assert out["pr_info"] is None


def test_normalize_issue_nested_non_list_comments_becomes_empty():
    data = {
        "issue_info": {"number": 3, "title": "t"},
        "comments": "not-a-list",
    }
    out = normalize_issue_json(data)
    assert out["comments"] == []


def test_normalize_pr_nested_non_list_comments_and_reviews():
    data = {
        "pr_info": {"number": 4},
        "comments": {},
        "reviews": "x",
    }
    out = normalize_pr_json(data)
    assert out["comments"] == []
    assert out["reviews"] == []
