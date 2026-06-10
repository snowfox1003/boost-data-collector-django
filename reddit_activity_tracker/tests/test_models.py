"""Tests for reddit_activity_tracker models."""

import pytest
from django.db import IntegrityError
from model_bakery import baker

from reddit_activity_tracker.models import RedditComment, RedditSubmission


@pytest.mark.django_db
def test_reddit_submission_reddit_id_unique():
    baker.make(
        RedditSubmission,
        reddit_id="t3_abc123",
        subreddit="cpp",
        title="First",
        url="https://example.com",
        permalink="/r/cpp/comments/abc123/",
        created_utc=1700000000,
    )
    with pytest.raises(IntegrityError):
        baker.make(
            RedditSubmission,
            reddit_id="t3_abc123",
            subreddit="cpp",
            title="Duplicate",
            url="https://example.com/2",
            permalink="/r/cpp/comments/abc123/2/",
            created_utc=1700000001,
        )


@pytest.mark.django_db
def test_reddit_comment_cascade_delete():
    submission = baker.make(
        RedditSubmission,
        reddit_id="t3_sub001",
        subreddit="cpp",
        title="Post",
        url="https://example.com",
        permalink="/r/cpp/comments/sub001/",
        created_utc=1700000000,
    )
    baker.make(
        RedditComment,
        reddit_id="t1_cmt001",
        submission=submission,
        parent_id="t3_sub001",
        url="https://www.reddit.com/r/cpp/comments/sub001/cmt001/",
        created_utc=1700000100,
    )
    assert RedditComment.objects.filter(reddit_id="t1_cmt001").exists()
    submission.delete()
    assert not RedditComment.objects.filter(reddit_id="t1_cmt001").exists()


@pytest.mark.django_db
def test_reddit_submission_str():
    submission = baker.make(
        RedditSubmission,
        reddit_id="t3_str001",
        subreddit="cpp",
        title="Hello World",
        url="https://example.com",
        permalink="/r/cpp/comments/str001/",
        created_utc=1700000000,
    )
    assert "t3_str001" in str(submission)
    assert "Hello World" in str(submission)


@pytest.mark.django_db
def test_reddit_comment_str():
    submission = baker.make(
        RedditSubmission,
        reddit_id="t3_sub002",
        subreddit="cpp",
        title="Post",
        url="https://example.com",
        permalink="/r/cpp/comments/sub002/",
        created_utc=1700000000,
    )
    comment = baker.make(
        RedditComment,
        reddit_id="t1_cmt002",
        submission=submission,
        parent_id="t3_sub002",
        url="https://www.reddit.com/r/cpp/comments/sub002/cmt002/",
        created_utc=1700000100,
    )
    assert "t1_cmt002" in str(comment)
    assert "t3_sub002" in str(comment)
