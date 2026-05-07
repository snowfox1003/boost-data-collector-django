"""Branch coverage for dashboard HTML builders beyond test_renderer happy path."""

from __future__ import annotations

import json
from unittest.mock import patch

from boost_library_usage_dashboard.dashboard_html import generate_dashboard_html


def _base_payload():
    return {
        "repos_by_year": {"2023": 2},
        "repos_by_version": [{"version": "1.83.0", "count": 7}],
        "repos_by_year_boost_rate": [
            {
                "year": "2024",
                "cpp_repo_count": 50,
                "over_10": 10,
                "boost_over_10": 3,
                "boost_over_10_percentage": "not-a-number",
            },
        ],
        "language_comparison_data": {
            "C++": {"2023": {"all": 100, "stars_10_plus": 40}},
            "Rust": {"2023": {"all": 200, "stars_10_plus": 80}},
        },
        "metrics_by_library": [
            {
                "name": "filesystem",
                "repo_count": 1,
                "total_usage": 1,
                "activity_score": 0.0,
            },
        ],
        "top_repositories": {
            "top20_by_stars": [],
            "top20_by_usage": [],
            "top20_by_created": [],
        },
        "libraries_page_data": {
            "filesystem": {
                "over_view": {"used_headers": {}},
                "external_consumers": {"table_data": [], "chart_data": {}},
                "contribute_data": {"table_data": [], "chart_data": {}},
                "internal_dependents_data": {
                    "table_data": [],
                    "chart_data": {
                        "1.83.0": "not-a-dict",
                        "1.84.0": {"first_level": 2, "all_deeper": 5},
                    },
                },
            },
            "emptylib": {},
        },
        "all_versions_for_chart": ["1.83.0"],
    }


def test_generate_dashboard_html_covers_index_and_library_branches(tmp_path):
    data_file = tmp_path / "dashboard_data.json"
    data_file.write_text(json.dumps(_base_payload()), encoding="utf-8")

    lib_dir = tmp_path / "libraries"
    generate_dashboard_html(
        dashboard_data_file=data_file,
        output_dir=tmp_path,
        libraries_dir=lib_dir,
    )

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Language Comparison by Year" in index_html
    assert "C++" in index_html and "Rust" in index_html

    fs_html = (lib_dir / "filesystem.html").read_text(encoding="utf-8")
    assert "filesystem" in fs_html

    assert not (lib_dir / "emptylib.html").exists()


def test_build_library_page_ext_chart_int_year_keys(tmp_path):
    """Integer keys in chart_data are lost through JSON; patch loads to preserve them.

    ``build_library_page`` uses ``ext_chart.get(y, ext_chart.get(int(y), {}))`` where
    ``y`` is the string year. Keys stored as int (e.g. 2024) miss ``.get(y)`` and hit
    the ``int(y)`` fallback — only possible if data is not round-tripped through JSON.
    """
    payload = _base_payload()
    payload["libraries_page_data"] = {
        "filesystem": {
            "over_view": {"used_headers": {}},
            "external_consumers": {
                "table_data": [],
                "chart_data": {
                    2024: {"repos": 1, "by_created": 2, "by_last_commit": 3},
                },
            },
            "contribute_data": {"table_data": [], "chart_data": {}},
            "internal_dependents_data": {"table_data": [], "chart_data": {}},
        },
    }
    data_file = tmp_path / "dashboard_data.json"
    data_file.write_text("{}", encoding="utf-8")
    with patch(
        "boost_library_usage_dashboard.dashboard_html.json.loads",
        return_value=payload,
    ):
        generate_dashboard_html(data_file, tmp_path, tmp_path / "libraries")
    html = (tmp_path / "libraries" / "filesystem.html").read_text(encoding="utf-8")
    assert "filesystem" in html
