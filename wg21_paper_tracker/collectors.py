"""WG21 paper tracker collector (pipeline + optional GitHub repository_dispatch)."""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.management.base import CommandError

from core.collectors import AbstractCollector
from wg21_paper_tracker.pipeline import (
    _normalize_mailing_date_label,
    run_tracker_pipeline,
)

logger = logging.getLogger(__name__)

GITHUB_DISPATCH_URL = "https://api.github.com/repos/{repo}/dispatches"


def trigger_github_repository_dispatch(
    repo: str,
    event_type: str,
    token: str,
    paper_urls: list[str],
) -> None:
    """POST repository_dispatch with client_payload {"papers": [<url>, ...]}."""
    url = GITHUB_DISPATCH_URL.format(repo=repo.strip())
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token.strip()}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = {
        "event_type": event_type,
        "client_payload": {"papers": paper_urls},
    }
    logger.info(
        "Sending repository_dispatch to %s (event_type=%s, %d URLs).",
        repo,
        event_type,
        len(paper_urls),
    )
    response = requests.post(url, json=body, headers=headers, timeout=30)
    if not response.ok:
        logger.error(
            "GitHub repository_dispatch failed: %s %s",
            response.status_code,
            response.text,
        )
    response.raise_for_status()


class Wg21PaperTrackerCollector(AbstractCollector):
    """Fetch mailings, update DB, optionally dispatch to GitHub."""

    def __init__(
        self,
        *,
        dry_run: bool,
        from_date: str | None,
        to_date: str | None,
    ) -> None:
        self.dry_run = dry_run
        self.from_date = from_date
        self.to_date = to_date

    @property
    def name(self) -> str:
        return "wg21_paper_tracker"

    def validate_config(self) -> None:
        def _validated_bound(
            value: str, *, field_for_normalize: str, cli_flag: str
        ) -> str:
            try:
                normalized = _normalize_mailing_date_label(
                    value, field_name=field_for_normalize
                )
            except ValueError as e:
                raise CommandError(str(e)) from e
            month = int(normalized[5:7])
            if month < 1 or month > 12:
                raise CommandError(
                    f"Invalid --{cli_flag} {value!r}; month must be 01-12 (YYYY-MM)."
                )
            return normalized

        from_norm: str | None = None
        if self.from_date:
            from_norm = _validated_bound(
                self.from_date,
                field_for_normalize="from_mailing_date",
                cli_flag="from-date",
            )
        to_norm: str | None = None
        if self.to_date:
            to_norm = _validated_bound(
                self.to_date,
                field_for_normalize="to_mailing_date",
                cli_flag="to-date",
            )
        if from_norm is not None and to_norm is not None and from_norm > to_norm:
            raise CommandError(
                f"--from-date {self.from_date!r} must be earlier than or equal to "
                f"--to-date {self.to_date!r}."
            )

    def collect(self) -> None:
        if self.dry_run:
            if self.from_date or self.to_date:
                logger.info(
                    "Dry run: skipping pipeline and GitHub dispatch "
                    "(from=%r, to=%r).",
                    self.from_date,
                    self.to_date,
                )
            else:
                logger.info("Dry run: skipping pipeline and GitHub dispatch.")
            return

        logger.info("Starting WG21 Paper Tracker...")

        try:
            result = run_tracker_pipeline(
                from_mailing_date=self.from_date,
                to_mailing_date=self.to_date,
            )
            n = result.new_paper_count
            logger.info("Recorded %d new paper(s); %d URL(s) for dispatch.", n, n)

            if not n:
                logger.info("No new papers in this run. Skipping GitHub dispatch.")
                return

            repo = getattr(settings, "WG21_GITHUB_DISPATCH_REPO", "") or ""
            token = getattr(settings, "WG21_GITHUB_DISPATCH_TOKEN", "") or ""
            enabled = getattr(settings, "WG21_GITHUB_DISPATCH_ENABLED", False)
            event_type = getattr(
                settings,
                "WG21_GITHUB_DISPATCH_EVENT_TYPE",
                "wg21_papers_convert",
            )

            if not enabled or not repo or not token:
                logger.warning(
                    "Skipping GitHub dispatch: set WG21_GITHUB_DISPATCH_ENABLED=True "
                    "and configure WG21_GITHUB_DISPATCH_REPO and "
                    "WG21_GITHUB_DISPATCH_TOKEN."
                )
                return
            trigger_github_repository_dispatch(
                repo,
                event_type,
                token,
                list(result.new_paper_urls),
            )
            logger.info("repository_dispatch sent successfully.")

        except ValueError as e:
            raise CommandError(str(e)) from e
