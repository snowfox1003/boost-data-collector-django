"""Integration tests for RedditActivityTrackerCollector."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from reddit_activity_tracker.management.commands.run_reddit_activity_tracker import (
    RedditActivityTrackerCollector,
)
from reddit_activity_tracker.models import RedditComment, RedditSubmission


@pytest.mark.django_db
@override_settings(
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
    REDDIT_USER_AGENT="test/1.0",
    WORKSPACE_DIR="/tmp/reddit_collector_test",
)
@patch(
    "reddit_activity_tracker.management.commands.run_reddit_activity_tracker.build_session"
)
def test_collector_end_to_end(mock_build_session, tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    session = MagicMock()
    session.fetch_user_about.return_value = {
        "id": "abc123",
        "name": "Taladar",
        "subreddit": {"title": "Taladar"},
    }
    session.fetch_submissions_in_range.return_value = [
        {
            "id": "7i8fbd",
            "subreddit": "cpp",
            "author": "Taladar",
            "author_fullname": "t2_abc123",
            "title": "Winsock Chat server and client",
            "selftext": "",
            "selftext_html": "",
            "url": "https://github.com/example/repo",
            "permalink": "/r/cpp/comments/7i8fbd/winsock/",
            "score": 0,
            "num_comments": 1,
            "created_utc": 1512670704,
        }
    ]
    session.fetch_comments_in_range.return_value = [
        {
            "id": "1h3p",
            "author": "Taladar",
            "author_fullname": "t2_abc123",
            "parent_id": "t3_7i8fbd",
            "link_id": "t3_7i8fbd",
            "body": "Nice post",
            "score": 1,
            "created_utc": 1512670800,
        }
    ]
    mock_build_session.return_value = session

    collector = RedditActivityTrackerCollector(options={"since": "2017-12-01"})
    result = collector.run()

    assert result.success is True
    assert result.counts["submissions"] == 1
    assert result.counts["comments"] == 1
    assert RedditSubmission.objects.filter(reddit_submission_id="t3_7i8fbd").exists()
    assert RedditComment.objects.filter(reddit_comment_id="t1_1h3p").exists()
    assert (
        tmp_path / "reddit_activity_tracker" / "submissions" / "t3_7i8fbd.json"
    ).exists()
    assert (tmp_path / "reddit_activity_tracker" / "comments" / "t1_1h3p.json").exists()


@pytest.mark.django_db
@patch(
    "reddit_activity_tracker.management.commands.run_reddit_activity_tracker.build_session"
)
def test_run_command_success(mock_build_session):
    session = MagicMock()
    session.fetch_submissions_in_range.return_value = []
    session.fetch_comments_in_range.return_value = []
    mock_build_session.return_value = session
    out = StringIO()
    call_command("run_reddit_activity_tracker", stdout=out, verbosity=0)
    assert "Collector finished" in out.getvalue() or out.getvalue() == ""
    mock_build_session.assert_called()
