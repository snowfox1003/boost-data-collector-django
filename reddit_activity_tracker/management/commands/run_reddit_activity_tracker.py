"""Management command: run_reddit_activity_tracker"""

from __future__ import annotations

import logging
from typing import Any

from core.collectors import AbstractCollector, BaseCollectorCommand
from core.protocols import TrackerResult
from core.tracker_result import GenericTrackerResult

from reddit_activity_tracker.fetcher import build_session

logger = logging.getLogger(__name__)


class RedditActivityTrackerCollector(AbstractCollector):
    """Collector stub — full fetch/upsert pipeline ships in PR2."""

    def __init__(self, *, stdout: Any, style: Any) -> None:
        self.stdout = stdout
        self.style = style

    @property
    def name(self) -> str:
        return "reddit_activity_tracker"

    def validate_config(self) -> None:
        build_session()

    def collect(self) -> TrackerResult:
        logger.info("run_reddit_activity_tracker: stub — fetch/upsert in PR2")
        self.stdout.write(
            self.style.SUCCESS("reddit_activity_tracker completed (stub)")
        )
        logger.info("run_reddit_activity_tracker: finished successfully")
        return GenericTrackerResult.ok()


class Command(BaseCollectorCommand):
    help = "Run the reddit_activity_tracker collector (stub)."

    def get_collector(self, **_options: Any) -> AbstractCollector:
        return RedditActivityTrackerCollector(stdout=self.stdout, style=self.style)
