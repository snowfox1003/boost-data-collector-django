"""Tests for reddit_activity_tracker.workspace."""

import json

import pytest
from django.test import override_settings
from model_bakery import baker

from cppa_user_tracker.models import RedditUser
from reddit_activity_tracker.models import RedditComment, RedditSubmission
from reddit_activity_tracker.workspace import (
    get_comment_json_path,
    get_submission_json_path,
    get_user_json_path,
    write_comment_json,
    write_submission_json,
    write_user_json,
)


@pytest.mark.django_db
@override_settings(WORKSPACE_DIR="/tmp/reddit_workspace_test")
def test_write_user_json_creates_file(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    user = baker.make(
        RedditUser,
        username="Taladar",
        reddit_user_id="t2_abc123",
        display_name="Taladar",
    )
    path = write_user_json(user)
    assert path == get_user_json_path("Taladar")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["username"] == "Taladar"
    assert payload["reddit_user_id"] == "t2_abc123"


@pytest.mark.django_db
@override_settings(WORKSPACE_DIR="/tmp/reddit_workspace_test")
def test_write_submission_json_overwrites(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    submission = baker.make(
        RedditSubmission,
        reddit_submission_id="t3_7i8fbd",
        subreddit="cpp",
        title="First",
        url="https://example.com",
        permalink="/r/cpp/comments/7i8fbd/",
        created_utc=1512670704,
        score=0,
    )
    write_submission_json(submission)
    submission.score = 10
    submission.save()
    path = write_submission_json(submission)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["reddit_submission_id"] == "t3_7i8fbd"
    assert payload["score"] == 10
    assert path == get_submission_json_path("t3_7i8fbd")


@pytest.mark.django_db
@override_settings(WORKSPACE_DIR="/tmp/reddit_workspace_test")
def test_write_comment_json(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    submission = baker.make(
        RedditSubmission,
        reddit_submission_id="t3_sub",
        subreddit="cpp",
        title="Post",
        url="https://example.com",
        permalink="/r/cpp/comments/sub/",
        created_utc=100,
    )
    comment = baker.make(
        RedditComment,
        reddit_comment_id="t1_cmt",
        submission=submission,
        parent_id="t3_sub",
        body="hello",
        url="https://example.com/c",
        created_utc=200,
    )
    path = write_comment_json(comment)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["reddit_comment_id"] == "t1_cmt"
    assert payload["submission_id"] == "t3_sub"
    assert path == get_comment_json_path("t1_cmt")
