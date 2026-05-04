"""Boost library usage dashboard collector."""

import logging

from django.conf import settings
from django.core.management.base import CommandError

from core.collectors.base import CollectorBase
from boost_library_usage_dashboard.analyzer import BoostUsageDashboardAnalyzer
from boost_library_usage_dashboard.publisher import publish_dashboard
from boost_library_usage_dashboard.renderer import render_dashboard_html
from boost_library_usage_dashboard.report import write_summary_report
from config.workspace import get_workspace_path

logger = logging.getLogger(__name__)


class BoostLibraryUsageDashboardCollector(CollectorBase):
    """Collect metrics, render HTML, optionally publish to GitHub."""

    def __init__(
        self,
        *,
        skip_collect: bool,
        skip_render: bool,
        skip_publish: bool,
        owner: str,
        repo: str,
        branch: str,
    ) -> None:
        self.skip_collect = skip_collect
        self.skip_render = skip_render
        self.skip_publish = skip_publish
        self.owner = owner
        self.repo = repo
        self.branch = branch

    def run(self) -> None:
        output_dir = get_workspace_path("boost_library_usage_dashboard").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.skip_collect:
            logger.info("Step 1: Collecting dashboard data from PostgreSQL...")
            analyzer = BoostUsageDashboardAnalyzer(output_dir=output_dir)
            stats = analyzer.run()

            logger.info("Step 2: Writing Markdown report...")
            write_summary_report(
                analyzer.report_file,
                stats,
                stars_min_threshold=analyzer.stars_min_threshold,
            )

        if not self.skip_render:
            logger.info("Step 3: Rendering HTML files...")
            render_dashboard_html(base_dir=settings.BASE_DIR, output_dir=output_dir)

        if not self.skip_collect or not self.skip_render:
            logger.info("Dashboard artifacts at: %s", output_dir)

        if not self.skip_publish:
            owner = (self.owner or "").strip() or (
                getattr(settings, "BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_OWNER", "")
                or ""
            ).strip()
            repo = (self.repo or "").strip() or (
                getattr(settings, "BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_REPO", "")
                or ""
            ).strip()
            branch = (
                (self.branch or "").strip()
                or (
                    getattr(
                        settings,
                        "BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_BRANCH",
                        "",
                    )
                    or ""
                ).strip()
                or "main"
            )

            if not owner or not repo:
                logger.warning(
                    "Skipping publish: set BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_OWNER "
                    "and BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_REPO in settings, or pass "
                    "--owner and --repo."
                )
            else:
                if not any(output_dir.rglob("*.html")):
                    raise CommandError(
                        "Refusing to publish: no HTML artifacts were found in "
                        f"{output_dir}. Run without --skip-render first."
                    )
                publish_dashboard(
                    output_dir=output_dir,
                    owner=owner,
                    repo=repo,
                    branch=branch,
                )
