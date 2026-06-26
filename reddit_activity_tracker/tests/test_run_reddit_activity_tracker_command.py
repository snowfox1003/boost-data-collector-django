"""Smoke test for run_reddit_activity_tracker."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings


@patch(
    "reddit_activity_tracker.management.commands.run_reddit_activity_tracker.build_session"
)
@pytest.mark.django_db
@override_settings(
    REDDIT_CLIENT_ID="cid",
    REDDIT_CLIENT_SECRET="secret",
    REDDIT_USER_AGENT="test/1.0",
    REDDIT_SUBREDDITS=["cpp"],
)
def test_run_reddit_activity_tracker_writes_success(mock_build_session):
    session = MagicMock()
    session.fetch_submissions_in_range.return_value = []
    session.fetch_comments_in_range.return_value = []
    mock_build_session.return_value = session
    out = StringIO()
    call_command("run_reddit_activity_tracker", stdout=out, verbosity=0)
    mock_build_session.assert_called_once()
    session.fetch_submissions_in_range.assert_called_once()
    session.fetch_comments_in_range.assert_called_once()
    assert session.fetch_submissions_in_range.call_args.kwargs["subreddit"] == "cpp"
