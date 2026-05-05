"""
Management command for WG21 Paper Tracker.
Runs the pipeline to fetch new mailings, upsert paper metadata in the DB, and optionally
trigger a GitHub repository_dispatch so another repo can download and convert documents.
"""

from core.collectors.command_base import BaseCollectorCommand
from wg21_paper_tracker.collectors import Wg21PaperTrackerCollector


class Command(BaseCollectorCommand):
    """Run WG21 paper tracker and optionally trigger GitHub repository_dispatch."""

    help = (
        "Run WG21 paper tracker (scrape, DB update) and send new paper URLs via "
        "repository_dispatch when enabled."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only log what would be done; do not run the pipeline or dispatch.",
        )
        parser.add_argument(
            "--from-date",
            dest="from_date",
            metavar="YYYY-MM",
            default=None,
            help=(
                "Process mailings with mailing_date >= YYYY-MM (WG21 / CSV style). "
                "Backfills from that mailing onward; without --to-date, no upper cap."
            ),
        )
        parser.add_argument(
            "--to-date",
            dest="to_date",
            metavar="YYYY-MM",
            default=None,
            help=(
                "Upper bound: mailing_date <= YYYY-MM. With --from-date, inclusive range; "
                "without --from-date, still only mailings newer than DB latest (capped at to)."
            ),
        )

    def get_collector(self, **options):
        dry_run = options.get("dry_run", False)
        from_date = options.get("from_date")
        to_date = options.get("to_date")
        if from_date is not None:
            from_date = from_date.strip()
            if not from_date:
                from_date = None
        if to_date is not None:
            to_date = to_date.strip()
            if not to_date:
                to_date = None
        return Wg21PaperTrackerCollector(
            dry_run=dry_run,
            from_date=from_date,
            to_date=to_date,
        )
