"""Build the Boost library usage dashboard from DB data and optionally publish to GitHub."""

from core.collectors import AbstractCollector, BaseCollectorCommand
from boost_library_usage_dashboard.collectors import (
    BoostLibraryUsageDashboardCollector,
)


class Command(BaseCollectorCommand):
    """Django management command: collect metrics, render HTML, optionally push to GitHub."""

    help = (
        "Generate Boost library usage report/dashboard from PostgreSQL data, "
        "then publish generated files to a target GitHub repository unless skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-collect",
            action="store_true",
            help="Skip PostgreSQL collection and Markdown report generation.",
        )
        parser.add_argument(
            "--skip-render",
            action="store_true",
            help="Skip HTML rendering.",
        )
        parser.add_argument(
            "--skip-publish",
            action="store_true",
            help="Skip publishing to the configured GitHub repository.",
        )
        parser.add_argument(
            "--owner",
            type=str,
            default="",
            help="Publish repo owner (overrides BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_OWNER).",
        )
        parser.add_argument(
            "--repo",
            type=str,
            default="",
            help="Publish repo name (overrides BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_REPO).",
        )
        parser.add_argument(
            "--branch",
            type=str,
            default="",
            help="Branch to publish to (overrides BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_BRANCH; default main).",
        )

    def get_collector(self, **options) -> AbstractCollector:
        return BoostLibraryUsageDashboardCollector(
            skip_collect=options["skip_collect"],
            skip_render=options["skip_render"],
            skip_publish=options["skip_publish"],
            owner=options["owner"],
            repo=options["repo"],
            branch=options["branch"],
        )
