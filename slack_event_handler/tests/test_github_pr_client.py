"""Tests for slack_event_handler.utils.github_pr_client."""

from unittest.mock import MagicMock, patch

import pytest

import slack_event_handler.utils.github_pr_client as gh_client


@pytest.fixture(autouse=True)
def reset_github_singleton():
    gh_client._gh = None
    yield
    gh_client._gh = None


@pytest.mark.django_db
def test_get_client_requires_token(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = ""
    gh_client._gh = None
    with pytest.raises(ValueError, match="SLACK_PR_BOT_GITHUB_TOKEN"):
        gh_client._get_client()


@pytest.mark.django_db
def test_post_pr_comment_uses_template_and_returns(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "ghp_secret"
    settings.SLACK_PR_BOT_COMMENT_TEMPLATE = "Hello from test"

    mock_pull = MagicMock()
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pull
    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch.object(gh_client, "Github", return_value=mock_gh):
        gh_client._gh = None
        gh_client.post_pr_comment("o", "r", 99)

    mock_repo.get_pull.assert_called_once_with(99)
    mock_pull.create_issue_comment.assert_called_once_with("Hello from test")


@pytest.mark.django_db
def test_post_pr_comment_retries_then_raises(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"
    from github.GithubException import GithubException

    mock_pull = MagicMock()
    mock_pull.create_issue_comment.side_effect = GithubException(500, "fail", {})
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pull
    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch.object(gh_client, "Github", return_value=mock_gh):
        gh_client._gh = None
        with patch.object(gh_client.time, "sleep"):
            with pytest.raises(GithubException):
                gh_client.post_pr_comment("a", "b", 1)

    assert mock_pull.create_issue_comment.call_count == gh_client.MAX_RETRIES
