"""Management command: run_reddit_activity_tracker"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings

from core.collectors import AbstractCollector, BaseCollectorCommand
from core.protocols import TrackerResult
from core.tracker_result import GenericTrackerResult
from reddit_activity_tracker.fetcher import RedditSession, build_session
from reddit_activity_tracker.models import RedditSubmission
from reddit_activity_tracker.services import (
    get_latest_comment_created_utc,
    get_latest_submission_created_utc,
    resolve_submission_for_comment,
    upsert_reddit_comment,
    upsert_reddit_submission,
)
from reddit_activity_tracker.workspace import (
    write_comment_json,
    write_submission_json,
    write_user_json,
)

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 30


def _parse_since(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    try:
        if "T" in raw or " " in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(raw, "%Y-%m-%d")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp())
    except ValueError as exc:
        raise ValueError(
            f"Invalid --since value {value!r}; use YYYY-MM-DD or ISO datetime"
        ) from exc


def _default_lookback_start() -> int:
    lookback_days = getattr(
        settings, "REDDIT_DEFAULT_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS
    )
    start = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    return int(start.timestamp())


def _resolve_submission_start_ts(options: dict[str, Any]) -> int:
    since_override = _parse_since(options.get("since"))
    if since_override is not None:
        return since_override

    latest = get_latest_submission_created_utc()
    if latest > 0:
        return latest

    return _default_lookback_start()


def _resolve_comment_start_ts(options: dict[str, Any]) -> int:
    since_override = _parse_since(options.get("since"))
    if since_override is not None:
        return since_override

    latest = get_latest_comment_created_utc()
    if latest > 0:
        return latest

    return _default_lookback_start()


def _record_user(
    user,
    seen_users: set[int],
    counts: dict[str, int],
) -> None:
    if user is None or user.pk in seen_users:
        return
    write_user_json(user)
    seen_users.add(user.pk)
    counts["users"] += 1


class RedditActivityTrackerCollector(AbstractCollector):
    """Scrape r/cpp submissions and comments for the incremental time window."""

    def __init__(self, *, options: dict[str, Any]) -> None:
        self.options = options
        self._session: RedditSession | None = None
        self._counts = {
            "submissions": 0,
            "comments": 0,
            "users": 0,
        }

    @property
    def name(self) -> str:
        return "reddit_activity_tracker"

    def validate_config(self) -> None:
        self._session = build_session()

    def collect(self) -> TrackerResult:
        if self._session is None:
            self._session = build_session()

        submission_start_ts = _resolve_submission_start_ts(self.options)
        comment_start_ts = _resolve_comment_start_ts(self.options)
        end_ts = int(time.time())
        logger.info(
            "reddit_activity_tracker: submission window %d..%d, comment window %d..%d (UTC)",
            submission_start_ts,
            end_ts,
            comment_start_ts,
            end_ts,
        )

        posts = self._session.fetch_submissions_in_range(submission_start_ts, end_ts)
        comments_data = self._session.fetch_comments_in_range(comment_start_ts, end_ts)

        submissions_by_id: dict[str, RedditSubmission] = {}
        seen_users: set[int] = set()

        for post in posts:
            submission = upsert_reddit_submission(post, session=self._session)
            write_submission_json(submission)
            submissions_by_id[post["id"]] = submission
            self._counts["submissions"] += 1
            _record_user(submission.user, seen_users, self._counts)

        for comment_data in comments_data:
            submission = resolve_submission_for_comment(
                comment_data,
                submissions_by_id,
            )
            comment = upsert_reddit_comment(
                comment_data,
                submission,
                session=self._session,
            )
            write_comment_json(comment)
            self._counts["comments"] += 1
            _record_user(comment.user, seen_users, self._counts)

        logger.info(
            "reddit_activity_tracker: finished submissions=%d comments=%d users=%d",
            self._counts["submissions"],
            self._counts["comments"],
            self._counts["users"],
        )
        return GenericTrackerResult.ok(**self._counts)


class Command(BaseCollectorCommand):
    help = "Run reddit_activity_tracker: scrape r/cpp submissions and comments."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help="Override start date (YYYY-MM-DD or ISO datetime). Default: latest DB timestamp.",
        )

    def get_collector(self, **options: Any) -> AbstractCollector:
        return RedditActivityTrackerCollector(options=options)
