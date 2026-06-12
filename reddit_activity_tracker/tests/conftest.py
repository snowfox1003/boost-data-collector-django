"""Shared fixtures for reddit_activity_tracker tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from reddit_activity_tracker.fetcher import RedditSession


@pytest.fixture
def reddit_session() -> RedditSession:
    return RedditSession("cid", "secret", "test/1.0")


@pytest.fixture
def sample_submission_payload() -> dict:
    return {
        "id": "7i8fbd",
        "name": "t3_7i8fbd",
        "subreddit": "cpp",
        "author": "Taladar",
        "author_fullname": "t2_abc123",
        "title": "Winsock Chat server and client",
        "selftext": "",
        "selftext_html": "",
        "url": "https://github.com/VedantParanjape/Chat-Server-and-Client",
        "permalink": "/r/cpp/comments/7i8fbd/winsock_chat_server_and_client/",
        "score": 0,
        "num_comments": 8,
        "created_utc": 1512670704,
    }


@pytest.fixture
def sample_comment_payload() -> dict:
    return {
        "id": "1h3p",
        "name": "t1_1h3p",
        "author": "Taladar",
        "author_fullname": "t2_abc123",
        "parent_id": "t3_7ijpx",
        "body": "I call bullshit.",
        "score": 1,
        "created_utc": 1229786861,
    }


@pytest.fixture
def mock_user_about() -> dict:
    return {
        "id": "abc123",
        "name": "Taladar",
        "subreddit": {"title": "Taladar"},
    }


@pytest.fixture
def mock_reddit_session(mock_user_about: dict) -> MagicMock:
    session = MagicMock(spec=RedditSession)
    session.fetch_user_about.return_value = mock_user_about
    session.get.return_value = {"data": {"children": []}}
    return session
