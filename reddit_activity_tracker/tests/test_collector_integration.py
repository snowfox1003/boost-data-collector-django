"""Integration tests for RedditActivityTrackerCollector."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from reddit_activity_tracker.management.commands.run_reddit_activity_tracker import (
    RedditActivityTrackerCollector,
    _filter_comments_by_keywords,
    _filter_submissions_by_keywords,
)
from reddit_activity_tracker.models import RedditComment, RedditSubmission


@pytest.mark.django_db
@override_settings(
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
    REDDIT_USER_AGENT="test/1.0",
    REDDIT_SUBREDDITS=["cpp"],
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
    session.fetch_submissions_in_range.assert_called_once()
    session.fetch_comments_in_range.assert_called_once()
    assert session.fetch_submissions_in_range.call_args.kwargs["subreddit"] == "cpp"


@pytest.mark.django_db
@override_settings(
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
    REDDIT_USER_AGENT="test/1.0",
    REDDIT_SUBREDDITS=["cpp", "cpp_questions"],
    WORKSPACE_DIR="/tmp/reddit_collector_test",
)
@patch(
    "reddit_activity_tracker.management.commands.run_reddit_activity_tracker.build_session"
)
def test_collector_iterates_multiple_subreddits(mock_build_session, tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    session = MagicMock()
    session.fetch_user_about.return_value = None
    session.fetch_submissions_in_range.side_effect = [
        [
            {
                "id": "cpp1",
                "subreddit": "cpp",
                "author": "user1",
                "title": "Cpp topic",
                "selftext": "",
                "url": "https://example.com/cpp",
                "permalink": "/r/cpp/comments/cpp1/",
                "score": 1,
                "num_comments": 0,
                "created_utc": 1512670704,
            }
        ],
        [
            {
                "id": "q1",
                "subreddit": "cpp_questions",
                "author": "user2",
                "title": "Question about templates",
                "selftext": "",
                "url": "https://example.com/q",
                "permalink": "/r/cpp_questions/comments/q1/",
                "score": 2,
                "num_comments": 0,
                "created_utc": 1512670800,
            }
        ],
    ]
    session.fetch_comments_in_range.return_value = []
    mock_build_session.return_value = session

    collector = RedditActivityTrackerCollector(options={"since": "2017-12-01"})
    result = collector.run()

    assert result.success is True
    assert result.counts["submissions"] == 2
    assert session.fetch_submissions_in_range.call_count == 2
    subreddit_args = [
        call.kwargs["subreddit"]
        for call in session.fetch_submissions_in_range.call_args_list
    ]
    assert subreddit_args == ["cpp", "cpp_questions"]
    assert RedditSubmission.objects.filter(subreddit="cpp").count() == 1
    assert RedditSubmission.objects.filter(subreddit="cpp_questions").count() == 1


@pytest.mark.django_db
@override_settings(
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
    REDDIT_USER_AGENT="test/1.0",
    REDDIT_SUBREDDITS=["programming"],
    REDDIT_SUBREDDIT_KEYWORD_FILTERS={"programming": ["boost", "c++", "cpp"]},
    WORKSPACE_DIR="/tmp/reddit_collector_test",
)
@patch(
    "reddit_activity_tracker.management.commands.run_reddit_activity_tracker.build_session"
)
def test_collector_keyword_filter_on_programming(
    mock_build_session, tmp_path, settings
):
    settings.WORKSPACE_DIR = str(tmp_path)
    session = MagicMock()
    session.fetch_user_about.return_value = None
    session.fetch_submissions_in_range.return_value = [
        {
            "id": "match",
            "subreddit": "programming",
            "author": "user1",
            "title": "Using Boost libraries in C++",
            "selftext": "",
            "url": "https://example.com/match",
            "permalink": "/r/programming/comments/match/",
            "score": 1,
            "num_comments": 0,
            "created_utc": 1512670704,
        },
        {
            "id": "skip",
            "subreddit": "programming",
            "author": "user2",
            "title": "Python asyncio tips",
            "selftext": "",
            "url": "https://example.com/skip",
            "permalink": "/r/programming/comments/skip/",
            "score": 2,
            "num_comments": 0,
            "created_utc": 1512670800,
        },
    ]
    session.fetch_comments_in_range.return_value = [
        {
            "id": "c1",
            "author": "user3",
            "link_id": "t3_match",
            "body": "Great C++ example",
            "score": 1,
            "created_utc": 1512670900,
        },
        {
            "id": "c2",
            "author": "user4",
            "link_id": "t3_skip",
            "body": "Try Java instead",
            "score": 0,
            "created_utc": 1512671000,
        },
    ]
    mock_build_session.return_value = session

    collector = RedditActivityTrackerCollector(options={"since": "2017-12-01"})
    result = collector.run()

    assert result.success is True
    assert result.counts["submissions"] == 1
    assert result.counts["comments"] == 1
    assert RedditSubmission.objects.filter(reddit_submission_id="t3_match").exists()
    assert not RedditSubmission.objects.filter(reddit_submission_id="t3_skip").exists()
    assert RedditComment.objects.filter(reddit_comment_id="t1_c1").exists()
    assert not RedditComment.objects.filter(reddit_comment_id="t1_c2").exists()


def test_filter_submissions_by_keywords():
    posts = [
        {"title": "Boost.Asio tutorial", "selftext": ""},
        {"title": "Python tips", "selftext": ""},
    ]
    filtered = _filter_submissions_by_keywords(posts, ["boost", "c++"])
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Boost.Asio tutorial"


def test_filter_comments_by_keywords():
    comments = [
        {"body": "Use std::vector in C++"},
        {"body": "Java is better"},
    ]
    filtered = _filter_comments_by_keywords(comments, ["c++"])
    assert len(filtered) == 1
    assert "C++" in filtered[0]["body"]


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


@pytest.mark.django_db
@override_settings(
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
    REDDIT_USER_AGENT="test/1.0",
    REDDIT_SUBREDDITS=["cpp", "programming"],
)
@patch(
    "reddit_activity_tracker.management.commands.run_reddit_activity_tracker.build_session"
)
def test_run_command_subreddits_override(mock_build_session):
    session = MagicMock()
    session.fetch_submissions_in_range.return_value = []
    session.fetch_comments_in_range.return_value = []
    mock_build_session.return_value = session

    call_command(
        "run_reddit_activity_tracker",
        subreddits="cpp_questions,learnprogramming",
        verbosity=0,
    )

    subreddit_args = [
        call.kwargs["subreddit"]
        for call in session.fetch_submissions_in_range.call_args_list
    ]
    assert subreddit_args == ["cpp_questions", "learnprogramming"]
