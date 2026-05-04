"""Unit tests for analyzer_output helpers."""

import json
from unittest.mock import MagicMock, patch

from boost_library_usage_dashboard.analyzer_output import (
    _created_at_key,
    collect_dashboard_data,
    collect_top_repositories_for_dashboard,
)


def test_created_at_key_orders_unknown_last():
    assert _created_at_key("") == (1, "")
    assert _created_at_key("2024-06-01") == (0, "2024-06-01")


def test_collect_top_repositories_for_dashboard_sorting():
    repos = [
        {"stars": 5, "usage_count": 100, "created_at": "2020-01-01"},
        {"stars": 50, "usage_count": 2, "created_at": "2021-05-05"},
        {"stars": "not-int", "usage_count": "x", "created_at": "2022-01-01"},
    ]
    top = collect_top_repositories_for_dashboard(repos)
    assert top["top20_by_stars"][0]["stars"] == 50
    assert top["top20_by_usage"][0]["usage_count"] == 100


def test_collect_dashboard_data_writes_json(tmp_path):
    analyzer = MagicMock()
    analyzer.output_dir = tmp_path
    analyzer.dashboard_data_file = tmp_path / "dashboard_data.json"
    analyzer.repo_info = [{"stars": 1, "usage_count": 1, "created_at": "2020-01-01"}]
    analyzer.version_name_list = ["1.74.0"]
    analyzer.filter_and_sort_libraries.return_value = []

    stats = {
        "repos_by_year": {"2024": 3},
        "version_related_stats": {
            "distribution_by_version": [
                {
                    "version": "1.74.0",
                    "created_at": "2024-01-01",
                    "confirmed": 2,
                    "guessed": 1,
                },
                ("1.34.0", "2023-01-01", 1, 0),
                [1],
            ],
        },
        "repos_by_year_boost_rate": [],
        "language_comparison_data": [],
    }

    with patch(
        "boost_library_usage_dashboard.analyzer_output.collect_libraries_page_data",
        return_value={"libraries": []},
    ):
        collect_dashboard_data(analyzer, stats)

    data = json.loads(analyzer.dashboard_data_file.read_text(encoding="utf-8"))
    assert "repos_by_version" in data
    assert "top_repositories" in data
