"""Direct tests for BoostLibraryUsageDashboardCollector orchestration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from boost_library_usage_dashboard.collectors import BoostLibraryUsageDashboardCollector


@pytest.mark.django_db
def test_collector_run_with_collect_and_render_skips_publish(tmp_path):
    fake_analyzer = MagicMock()
    fake_analyzer.run.return_value = {"total_repositories": 0}
    fake_analyzer.report_file = tmp_path / "Boost_Usage_Report_total.md"
    fake_analyzer.stars_min_threshold = 10

    with patch(
        "boost_library_usage_dashboard.collectors.get_workspace_path",
        return_value=tmp_path,
    ), patch(
        "boost_library_usage_dashboard.collectors.BoostUsageDashboardAnalyzer",
        return_value=fake_analyzer,
    ) as analyzer_cls, patch(
        "boost_library_usage_dashboard.collectors.write_summary_report"
    ) as write_report, patch(
        "boost_library_usage_dashboard.collectors.render_dashboard_html"
    ) as render_html, patch(
        "boost_library_usage_dashboard.collectors.publish_dashboard"
    ) as publish_mock:
        col = BoostLibraryUsageDashboardCollector(
            skip_collect=False,
            skip_render=False,
            skip_publish=True,
            owner="",
            repo="",
            branch="",
        )
        col.run()

    analyzer_cls.assert_called_once()
    fake_analyzer.run.assert_called_once()
    write_report.assert_called_once()
    expected = Path(str(tmp_path)).resolve()
    render_html.assert_called_once_with(
        base_dir=settings.BASE_DIR,
        output_dir=expected,
    )
    publish_mock.assert_not_called()
