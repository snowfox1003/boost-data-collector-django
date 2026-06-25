"""
Workspace paths and JSON writers for reddit_activity_tracker.

Layout:
  workspace/reddit_activity_tracker/users/{username}.json
  workspace/reddit_activity_tracker/submissions/{reddit_submission_id}.json
  workspace/reddit_activity_tracker/comments/{reddit_comment_id}.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config.workspace import get_workspace_path
from core.operations.file_ops import sanitize_filename
from cppa_user_tracker.models import RedditUser
from reddit_activity_tracker.models import RedditComment, RedditSubmission

_APP_SLUG = "reddit_activity_tracker"


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_workspace_root() -> Path:
    return get_workspace_path(_APP_SLUG)


def _users_dir() -> Path:
    path = get_workspace_root() / "users"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _submissions_dir() -> Path:
    path = get_workspace_root() / "submissions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _comments_dir() -> Path:
    path = get_workspace_root() / "comments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(value: str) -> str:
    cleaned = sanitize_filename((value or "").strip()).strip("_")
    return cleaned or "unknown"


def get_user_json_path(username: str) -> Path:
    return _users_dir() / f"{_slug(username)}.json"


def get_submission_json_path(reddit_submission_id: str) -> Path:
    return _submissions_dir() / f"{_slug(reddit_submission_id)}.json"


def get_comment_json_path(reddit_comment_id: str) -> Path:
    return _comments_dir() / f"{_slug(reddit_comment_id)}.json"


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def user_to_dict(user: RedditUser) -> dict:
    return {
        "reddit_user_id": user.reddit_user_id,
        "username": user.username,
        "display_name": user.display_name,
        "created_at": _iso(user.created_at),
        "updated_at": _iso(user.updated_at),
    }


def submission_to_dict(submission: RedditSubmission) -> dict:
    return {
        "reddit_submission_id": submission.reddit_submission_id,
        "subreddit": submission.subreddit,
        "user": submission.user.username if submission.user else None,
        "title": submission.title,
        "selftext": submission.selftext,
        "selftext_html": submission.selftext_html,
        "url": submission.url,
        "permalink": submission.permalink,
        "score": submission.score,
        "num_comments": submission.num_comments,
        "created_utc": submission.created_utc,
        "fetched_at": _iso(submission.fetched_at),
    }


def comment_to_dict(comment: RedditComment) -> dict:
    return {
        "reddit_comment_id": comment.reddit_comment_id,
        "submission_id": comment.submission.reddit_submission_id,
        "user": comment.user.username if comment.user else None,
        "parent_id": comment.parent_id,
        "body": comment.body,
        "url": comment.url,
        "score": comment.score,
        "created_utc": comment.created_utc,
        "fetched_at": _iso(comment.fetched_at),
    }


def write_user_json(user: RedditUser) -> Path:
    return _write_json(get_user_json_path(user.username), user_to_dict(user))


def write_submission_json(submission: RedditSubmission) -> Path:
    return _write_json(
        get_submission_json_path(submission.reddit_submission_id),
        submission_to_dict(submission),
    )


def write_comment_json(comment: RedditComment) -> Path:
    return _write_json(
        get_comment_json_path(comment.reddit_comment_id),
        comment_to_dict(comment),
    )
