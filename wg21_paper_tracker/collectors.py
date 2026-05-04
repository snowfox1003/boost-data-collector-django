"""WG21 paper tracker collector (pipeline + optional GitHub repository_dispatch)."""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.management.base import CommandError

from core.collectors.base import CollectorBase
from wg21_paper_tracker.pipeline import run_tracker_pipeline

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


class Wg21PaperTrackerCollector(CollectorBase):
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

    def run(self) -> None:
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
            try:
                trigger_github_repository_dispatch(
                    repo,
                    event_type,
                    token,
                    list(result.new_paper_urls),
                )
                logger.info("repository_dispatch sent successfully.")
            except Exception:
                logger.exception("Failed to send repository_dispatch.")
                raise

        except ValueError as e:
            raise CommandError(str(e)) from e
        except Exception as e:
            logger.exception("WG21 Paper Tracker failed: %s", e)
            raise
