"""
Service layer for reddit_activity_tracker.

All creates/updates/deletes for this app's models must go through functions in this
module. See CONTRIBUTING.md for the project-wide rule.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Max

from cppa_user_tracker.services import resolve_reddit_user_from_author_data

from reddit_activity_tracker.fetcher import SUBREDDIT, RedditSession
from reddit_activity_tracker.models import RedditComment, RedditSubmission


def submission_id_from_link_id(link_id: str) -> str | None:
    link_id = (link_id or "").strip()
    if link_id.startswith("t3_"):
        return link_id[3:] or None
    return link_id or None


@transaction.atomic
def get_or_create_submission_stub(
    submission_id: str,
    *,
    subreddit: str = "cpp",
) -> RedditSubmission:
    """Ensure a submission row exists for FK when only a comment link_id is known."""
    post_id = (submission_id or "").strip().removeprefix("t3_")
    if not post_id:
        raise ValueError("Submission id is required")

    reddit_submission_id = f"t3_{post_id}"
    permalink = f"/r/{subreddit}/comments/{post_id}/"
    submission, _created = RedditSubmission.objects.get_or_create(
        reddit_submission_id=reddit_submission_id,
        defaults={
            "subreddit": subreddit,
            "user": None,
            "title": "",
            "selftext": "",
            "selftext_html": "",
            "url": f"https://www.reddit.com{permalink}",
            "permalink": permalink,
            "score": 0,
            "num_comments": 0,
            "created_utc": 0,
        },
    )
    return submission


def resolve_submission_for_comment(
    comment_data: dict,
    submissions_by_id: dict[str, RedditSubmission],
) -> RedditSubmission:
    """Return the submission row for a period comment, creating a stub if needed."""
    post_id = submission_id_from_link_id(comment_data.get("link_id", ""))
    if not post_id:
        raise ValueError("Comment link_id is required")

    submission = submissions_by_id.get(post_id)
    if submission is not None:
        return submission

    reddit_submission_id = f"t3_{post_id}"
    existing = RedditSubmission.objects.filter(
        reddit_submission_id=reddit_submission_id
    ).first()
    if existing is not None:
        return existing

    return get_or_create_submission_stub(
        post_id,
        subreddit=(comment_data.get("subreddit") or SUBREDDIT).strip(),
    )


@transaction.atomic
def upsert_reddit_submission(
    data: dict[str, Any],
    *,
    session: RedditSession | None = None,
) -> RedditSubmission:
    """Update or create a submission keyed by reddit_submission_id."""
    post_id = (data.get("id") or "").strip()
    if not post_id:
        raise ValueError("Submission id is required")

    reddit_submission_id = (
        data.get("reddit_submission_id") or data.get("name") or f"t3_{post_id}"
    )
    if not str(reddit_submission_id).startswith("t3_"):
        reddit_submission_id = f"t3_{post_id}"

    user = resolve_reddit_user_from_author_data(data, client=session)
    defaults = {
        "subreddit": (data.get("subreddit") or "cpp").strip(),
        "user": user,
        "title": (data.get("title") or "")[:1024],
        "selftext": data.get("selftext") or "",
        "selftext_html": data.get("selftext_html") or "",
        "url": data.get("url") or f"https://www.reddit.com{data.get('permalink', '')}",
        "permalink": data.get("permalink") or "",
        "score": int(data.get("score") or 0),
        "num_comments": int(data.get("num_comments") or 0),
        "created_utc": int(data.get("created_utc") or 0),
    }

    submission, _created = RedditSubmission.objects.update_or_create(
        reddit_submission_id=reddit_submission_id,
        defaults=defaults,
    )
    return submission


@transaction.atomic
def upsert_reddit_comment(
    data: dict[str, Any],
    submission: RedditSubmission,
    *,
    session: RedditSession | None = None,
) -> RedditComment:
    """Update or create a comment keyed by reddit_comment_id."""
    comment_id = (data.get("id") or "").strip()
    if not comment_id:
        raise ValueError("Comment id is required")

    reddit_comment_id = (
        data.get("reddit_comment_id") or data.get("name") or f"t1_{comment_id}"
    )
    if not str(reddit_comment_id).startswith("t1_"):
        reddit_comment_id = f"t1_{comment_id}"

    user = resolve_reddit_user_from_author_data(data, client=session)
    permalink = (data.get("permalink") or "").strip()
    if permalink:
        url = (
            permalink
            if permalink.startswith("http")
            else f"https://www.reddit.com{permalink}"
        )
    else:
        submission_permalink = submission.permalink.rstrip("/")
        url = f"https://www.reddit.com{submission_permalink}/{comment_id}/"

    defaults = {
        "submission": submission,
        "user": user,
        "parent_id": data.get("parent_id") or "",
        "body": data.get("body") or "",
        "url": url,
        "score": int(data.get("score") or 0),
        "created_utc": int(data.get("created_utc") or 0),
    }

    comment, _created = RedditComment.objects.update_or_create(
        reddit_comment_id=reddit_comment_id,
        defaults=defaults,
    )
    return comment


def get_latest_submission_created_utc() -> int:
    """Return max created_utc across submissions, or 0 when empty."""
    latest = RedditSubmission.objects.aggregate(latest=Max("created_utc"))["latest"]
    return latest if latest is not None else 0


def get_latest_comment_created_utc() -> int:
    """Return max created_utc across comments, or 0 when empty."""
    latest = RedditComment.objects.aggregate(latest=Max("created_utc"))["latest"]
    return latest if latest is not None else 0
