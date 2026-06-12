"""Tests for reddit_activity_tracker.services."""

import pytest
from model_bakery import baker

from reddit_activity_tracker import services
from reddit_activity_tracker.models import RedditComment, RedditSubmission


@pytest.mark.django_db
def test_upsert_reddit_submission_creates_and_updates(
    sample_submission_payload, mock_reddit_session
):
    submission = services.upsert_reddit_submission(
        sample_submission_payload,
        session=mock_reddit_session,
    )
    assert submission.reddit_submission_id == "t3_7i8fbd"
    assert submission.user.username == "Taladar"

    sample_submission_payload["score"] = 5
    updated = services.upsert_reddit_submission(
        sample_submission_payload,
        session=mock_reddit_session,
    )
    assert updated.pk == submission.pk
    assert updated.score == 5


@pytest.mark.django_db
def test_upsert_reddit_comment_creates_and_updates(
    sample_submission_payload,
    sample_comment_payload,
    mock_reddit_session,
):
    submission = services.upsert_reddit_submission(
        sample_submission_payload,
        session=mock_reddit_session,
    )
    comment = services.upsert_reddit_comment(
        sample_comment_payload,
        submission,
        session=mock_reddit_session,
    )
    assert comment.reddit_comment_id == "t1_1h3p"
    assert comment.submission_id == submission.pk

    sample_comment_payload["score"] = 9
    updated = services.upsert_reddit_comment(
        sample_comment_payload,
        submission,
        session=mock_reddit_session,
    )
    assert updated.pk == comment.pk
    assert updated.score == 9


@pytest.mark.django_db
def test_submission_id_from_link_id():
    assert services.submission_id_from_link_id("t3_7ijpx") == "7ijpx"
    assert services.submission_id_from_link_id("") is None


@pytest.mark.django_db
def test_resolve_submission_for_comment_uses_stub():
    submission = services.resolve_submission_for_comment(
        {"link_id": "t3_oldpost", "subreddit": "cpp"},
        {},
    )
    assert submission.reddit_submission_id == "t3_oldpost"
    assert submission.title == ""


@pytest.mark.django_db
def test_get_or_create_submission_stub_creates_minimal_row():
    submission = services.get_or_create_submission_stub("7i8fbd")
    assert submission.reddit_submission_id == "t3_7i8fbd"
    assert submission.title == ""
    assert submission.created_utc == 0

    again = services.get_or_create_submission_stub("t3_7i8fbd")
    assert again.pk == submission.pk


@pytest.mark.django_db
def test_get_latest_submission_and_comment_created_utc_empty_db():
    assert services.get_latest_submission_created_utc() == 0
    assert services.get_latest_comment_created_utc() == 0


@pytest.mark.django_db
def test_get_latest_submission_and_comment_created_utc_independent():
    baker.make(
        RedditSubmission,
        reddit_submission_id="t3_a",
        subreddit="cpp",
        title="A",
        url="https://example.com/a",
        permalink="/r/cpp/comments/a/",
        created_utc=100,
    )
    baker.make(
        RedditComment,
        reddit_comment_id="t1_b",
        submission=RedditSubmission.objects.get(reddit_submission_id="t3_a"),
        parent_id="t3_a",
        url="https://example.com/b",
        created_utc=200,
    )
    assert services.get_latest_submission_created_utc() == 100
    assert services.get_latest_comment_created_utc() == 200
