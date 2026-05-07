"""Integration tests for BoostUsageDashboardAnalyzer with PostgreSQL/Django ORM."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from model_bakery import baker

from boost_library_tracker import services as bl_services
from boost_library_usage_dashboard.analyzer import BoostUsageDashboardAnalyzer
from boost_usage_tracker import services as bu_services
from github_activity_tracker import services as gh_services


@pytest.mark.django_db
def test_analyzer_run_writes_dashboard_json_and_stats(
    tmp_path: Path,
    github_account,
    github_file,
    boost_library,
):
    """Minimal repo + usage graph exercises analyzer pipeline including DB metrics."""
    v_old, _ = bl_services.get_or_create_boost_version(
        "boost-1.80.0",
        datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    v_new, _ = bl_services.get_or_create_boost_version(
        "boost-1.81.0",
        datetime(2021, 6, 1, tzinfo=timezone.utc),
    )
    bl_services.get_or_create_boost_library_version(
        boost_library,
        v_old,
        cpp_version="C++14",
        description="Old snap",
        key="algorithm-old",
        documentation="https://example.invalid/old",
    )
    bl_services.get_or_create_boost_library_version(
        boost_library,
        v_new,
        cpp_version="C++17",
        description="Algorithm library",
        key="algorithm",
        documentation="https://example.invalid/new",
    )

    boost_file, _ = bl_services.get_or_create_boost_file(github_file, boost_library)

    ext_repo_parent = baker.make(
        "github_activity_tracker.GitHubRepository",
        owner_account=github_account,
        repo_name="dash-consumer-" + uuid.uuid4().hex[:8],
        stars=11,
        repo_created_at=datetime(2024, 3, 15, tzinfo=timezone.utc),
    )
    ext_repo, _ = bu_services.get_or_create_boost_external_repo(
        ext_repo_parent,
        boost_version="boost-1.81.0",
        is_boost_used=True,
    )
    ext_file = baker.make(
        "github_activity_tracker.GitHubFile",
        repo=ext_repo_parent,
        filename="consumer.cpp",
    )
    bu_services.create_or_update_boost_usage(
        ext_repo,
        boost_file,
        ext_file,
        last_commit_date=datetime(2024, 4, 1, tzinfo=timezone.utc),
    )

    analyzer = BoostUsageDashboardAnalyzer(tmp_path)
    stats = analyzer.run()

    assert stats["total_repositories"] >= 1
    assert "version_related_stats" in stats
    assert (tmp_path / "dashboard_data.json").is_file()
    payload = json.loads((tmp_path / "dashboard_data.json").read_text(encoding="utf-8"))
    assert "metrics_by_library" in payload
    assert "libraries_page_data" in payload


@pytest.mark.django_db
def test_load_repository_count_from_db_merges_cpp_rows(tmp_path: Path):
    cpp, _ = gh_services.get_or_create_language("C++")
    gh_services.create_or_update_created_repos_by_language(
        language=cpp,
        year=2024,
        all_repos=100,
        significant_repos=40,
    )

    analyzer = BoostUsageDashboardAnalyzer(tmp_path)
    out = analyzer._load_repository_count_from_db(
        {"2024": 7}
    )  # pylint: disable=protected-access

    row_by_year = {r["year"]: r for r in out["repos_by_year_boost_rate"]}
    assert row_by_year["2024"]["boost_over_10"] == 7
    assert row_by_year["2024"]["over_10"] == 40
    assert row_by_year["2024"]["cpp_repo_count"] == 100
    assert "C++" in out["language_comparison_data"]


@pytest.mark.django_db
def test_load_repository_count_from_db_lookup_error_returns_empty(tmp_path: Path):
    analyzer = BoostUsageDashboardAnalyzer(tmp_path)
    with patch(
        "boost_library_usage_dashboard.analyzer.apps.get_model",
        side_effect=LookupError("no model"),
    ):
        out = analyzer._load_repository_count_from_db(
            {"2024": 1}
        )  # pylint: disable=protected-access
    assert out == {"repos_by_year_boost_rate": [], "language_comparison_data": {}}
