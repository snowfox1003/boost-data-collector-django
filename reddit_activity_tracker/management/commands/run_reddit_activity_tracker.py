"""Management command: run_reddit_activity_tracker"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings
from django.core.management.base import CommandError

from core.collectors import AbstractCollector, BaseCollectorCommand
from core.protocols import IncrementalState, TrackerResult
from core.tracker_result import GenericTrackerResult
from reddit_activity_tracker.fetcher import RedditSession, build_session
from reddit_activity_tracker.models import RedditSubmission
from reddit_activity_tracker.protocol_impl import RedditIncrementalState
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


def _parse_subreddit_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s.strip().removeprefix("r/") for s in raw.split(",") if s.strip()]


def _resolve_subreddit_targets(options: dict[str, Any]) -> list[str]:
    raw_override = options.get("subreddits")
    if raw_override and str(raw_override).strip():
        targets = _parse_subreddit_list(str(raw_override))
    else:
        targets = list(getattr(settings, "REDDIT_SUBREDDITS", []))
    targets = list(dict.fromkeys(targets))
    if not targets:
        raise CommandError(
            "No subreddit targets configured. Set REDDIT_SUBREDDITS or pass --subreddits."
        )
    return targets


def _get_keyword_filters() -> dict[str, list[str]]:
    return dict(getattr(settings, "REDDIT_SUBREDDIT_KEYWORD_FILTERS", {}))


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


def _filter_submissions_by_keywords(
    posts: list[dict],
    keywords: list[str],
) -> list[dict]:
    if not keywords:
        return posts
    filtered = []
    for post in posts:
        combined = f"{post.get('title', '')} {post.get('selftext', '')}"
        if _matches_keywords(combined, keywords):
            filtered.append(post)
    return filtered


def _filter_comments_by_keywords(
    comments: list[dict],
    keywords: list[str],
) -> list[dict]:
    if not keywords:
        return comments
    return [
        comment
        for comment in comments
        if _matches_keywords(comment.get("body", ""), keywords)
    ]


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


def _resolve_submission_start_ts(options: dict[str, Any], *, subreddit: str) -> int:
    since_override = _parse_since(options.get("since"))
    if since_override is not None:
        return since_override

    latest = get_latest_submission_created_utc(subreddit=subreddit)
    if latest > 0:
        return latest

    return _default_lookback_start()


def _resolve_comment_start_ts(options: dict[str, Any], *, subreddit: str) -> int:
    since_override = _parse_since(options.get("since"))
    if since_override is not None:
        return since_override

    latest = get_latest_comment_created_utc(subreddit=subreddit)
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
    """Scrape configured subreddits for submissions and comments incrementally."""

    def __init__(self, *, options: dict[str, Any]) -> None:
        self.options = options
        self._session: RedditSession | None = None
        self._subreddits: list[str] = []
        self._counts = {
            "submissions": 0,
            "comments": 0,
            "users": 0,
        }

    @property
    def name(self) -> str:
        return "reddit_activity_tracker"

    def validate_config(self) -> None:
        self._subreddits = _resolve_subreddit_targets(self.options)
        self._session = build_session()

    def load_incremental_state(self) -> IncrementalState | None:
        if not self._subreddits:
            self._subreddits = _resolve_subreddit_targets(self.options)
        submission_cursors = {
            name: get_latest_submission_created_utc(subreddit=name)
            for name in self._subreddits
        }
        comment_cursors = {
            name: get_latest_comment_created_utc(subreddit=name)
            for name in self._subreddits
        }
        return RedditIncrementalState.from_subreddit_cursors(
            submissions=submission_cursors,
            comments=comment_cursors,
        )

    def collect(self) -> TrackerResult:
        if self._session is None:
            self._session = build_session()
        if not self._subreddits:
            self._subreddits = _resolve_subreddit_targets(self.options)

        end_ts = int(time.time())
        keyword_filters = _get_keyword_filters()
        submissions_by_id: dict[str, RedditSubmission] = {}
        seen_users: set[int] = set()
        submission_cursors_out: dict[str, int] = {}
        comment_cursors_out: dict[str, int] = {}

        for subreddit in self._subreddits:
            submission_start_ts = _resolve_submission_start_ts(
                self.options,
                subreddit=subreddit,
            )
            comment_start_ts = _resolve_comment_start_ts(
                self.options,
                subreddit=subreddit,
            )
            keywords = keyword_filters.get(subreddit, [])

            logger.info(
                "reddit_activity_tracker: r/%s submission window %d..%d, "
                "comment window %d..%d (UTC)",
                subreddit,
                submission_start_ts,
                end_ts,
                comment_start_ts,
                end_ts,
            )

            posts = self._session.fetch_submissions_in_range(
                submission_start_ts,
                end_ts,
                subreddit=subreddit,
            )
            posts = _filter_submissions_by_keywords(posts, keywords)

            for post in posts:
                submission = upsert_reddit_submission(post, session=self._session)
                write_submission_json(submission)
                submissions_by_id[post["id"]] = submission
                self._counts["submissions"] += 1
                _record_user(submission.user, seen_users, self._counts)
                created = int(post.get("created_utc", 0))
                submission_cursors_out[subreddit] = max(
                    submission_cursors_out.get(subreddit, 0),
                    created,
                )

            comments_data = self._session.fetch_comments_in_range(
                comment_start_ts,
                end_ts,
                subreddit=subreddit,
            )
            comments_data = _filter_comments_by_keywords(comments_data, keywords)

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
                created = int(comment_data.get("created_utc", 0))
                comment_cursors_out[subreddit] = max(
                    comment_cursors_out.get(subreddit, 0),
                    created,
                )

            if subreddit not in submission_cursors_out:
                submission_cursors_out[subreddit] = get_latest_submission_created_utc(
                    subreddit=subreddit
                )
            if subreddit not in comment_cursors_out:
                comment_cursors_out[subreddit] = get_latest_comment_created_utc(
                    subreddit=subreddit
                )

        self._incremental_state_out = RedditIncrementalState.from_subreddit_cursors(
            submissions=submission_cursors_out,
            comments=comment_cursors_out,
        )

        logger.info(
            "reddit_activity_tracker: finished subreddits=%s submissions=%d "
            "comments=%d users=%d",
            ",".join(self._subreddits),
            self._counts["submissions"],
            self._counts["comments"],
            self._counts["users"],
        )
        return GenericTrackerResult.ok(**self._counts)


class Command(BaseCollectorCommand):
    help = (
        "Run reddit_activity_tracker: scrape configured subreddits for "
        "submissions and comments."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help="Override start date (YYYY-MM-DD or ISO datetime). Default: latest DB timestamp.",
        )
        parser.add_argument(
            "--subreddits",
            type=str,
            default=None,
            help="Comma-separated subreddit names (overrides REDDIT_SUBREDDITS setting).",
        )

    def get_collector(self, **options: Any) -> AbstractCollector:
        return RedditActivityTrackerCollector(options=options)
