"""Tests for pure helpers in boost_library_usage_dashboard.analyzer_libraries."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from boost_library_usage_dashboard.analyzer_libraries import (
    collect_commit_info_by_library,
    collect_libraries_page_data,
    build_library_overview_data,
    get_contribution_data,
    get_external_consumer_data,
    get_first_version_released_after,
    get_last_updated_version,
)


class _FakeVersion:
    def __init__(self, version: str, created_at: datetime | None) -> None:
        self.version = version
        self.version_created_at = created_at


def test_get_first_version_released_after_none_commit():
    v = _FakeVersion("boost-1.81.0", datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert get_first_version_released_after([v], None) is None


def test_get_first_version_released_after_no_candidates():
    v = _FakeVersion("boost-1.81.0", datetime(2024, 1, 1, tzinfo=timezone.utc))
    commit_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert get_first_version_released_after([v], commit_at) is None


def test_get_first_version_released_after_picks_earliest_future_release():
    v_early = _FakeVersion("boost-1.82.0", datetime(2023, 6, 1, tzinfo=timezone.utc))
    v_later = _FakeVersion("boost-1.83.0", datetime(2024, 6, 1, tzinfo=timezone.utc))
    commit_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert (
        get_first_version_released_after([v_later, v_early], commit_at)
        == "boost-1.82.0"
    )


def test_get_external_consumer_data_builds_table_and_chart():
    lib = {
        "top_repo_list": {"org/a": 2, "org/b": 1},
        "year_data": {
            "2024": {"created_count": 5, "last_commit_count": 3},
        },
    }
    repo_info_dict = {
        "org/a": {
            "stars": 100,
            "created_at": "2024-01-15T00:00:00",
            "pushed_at": "2024-06-01T00:00:00",
        },
        "org/b": {"stars": 10, "created_at": "", "pushed_at": ""},
    }
    out = get_external_consumer_data(lib, repo_info_dict)
    names = {row["name"] for row in out["table_data"]}
    assert names == {"org/a", "org/b"}
    assert out["chart_data"]["2024"]["by_created"] == 5
    assert out["chart_data"]["2024"]["repos"] == 1


def test_get_contribution_data_filters_chart_by_created_version():
    lib = {
        "created_version": "1.70.0",
        "contribute_data": {
            "1.65.0": {
                "count": 2,
                "persons": {"1": {"identity_name": "Old", "commit_count": 2}},
            },
            "1.80.0": {
                "count": 4,
                "persons": {
                    "2": {"identity_name": "New", "commit_count": 4},
                },
            },
        },
    }
    out = get_contribution_data(lib)
    assert any(row["version"] == "1.80.0" for row in out["table_data"])
    assert out["chart_data"] == {"1.80.0": 4}
    assert "1.65.0" not in out["chart_data"]


def test_get_last_updated_version_empty():
    assert get_last_updated_version({}) == ""


def test_get_last_updated_version_max_tuple():
    data = {
        "1.80.0": {"count": 2, "persons": {}},
        "1.84.0": {"count": 1, "persons": {}},
    }
    assert get_last_updated_version(data) == "1.84.0"


def test_build_library_overview_data_aggregates_chart():
    now_ret = MagicMock()
    now_ret.year = 2026
    lib_source = {
        "created_version": "1.70.0",
        "repo_count": 12,
        "activity_score": 1.2,
        "average_stars": 40,
        "description": "d",
        "used_headers": {"h.hpp": 3},
        "contribute_data": {
            "1.84.0": {
                "count": 2,
                "persons": {"10": {}, "11": {}},
            },
        },
    }
    lib_data = {
        "internal_dependents_data": {"table_data": [{"name": "x"}]},
        "external_consumers": {
            "chart_data": {
                "2024": {"repos": 5},
                "2025": {"repos": 3},
                "2026": {"repos": 12},
            },
        },
    }
    with patch("boost_library_usage_dashboard.analyzer_libraries.datetime") as dt_mock:
        dt_mock.now.return_value = now_ret
        overview = build_library_overview_data(lib_source, lib_data)
    assert overview["internal_consumers"] == 1
    assert overview["most_used_year"]["year"] == "2026"
    assert overview["most_used_year"]["count"] == 12
    assert overview["last_year_used_repo_count"]["year"] == 2025
    assert overview["last_year_used_repo_count"]["count"] == 3


def test_collect_libraries_page_data_wires_sections():
    analyzer = MagicMock()
    analyzer.library_info = [
        {
            "id": 7,
            "name": "asio",
            "top_repo_list": {},
            "year_data": {},
            "created_version": "1.72.0",
            "contribute_data": {},
        }
    ]
    analyzer.repo_info_dict = {}
    deps = {
        7: {"table_data": [{"name": "dep"}], "chart_data": {"boost-1.81.0": {}}},
    }
    with patch(
        "boost_library_usage_dashboard.analyzer_libraries.collect_dependents_data",
        return_value=deps,
    ):
        out = collect_libraries_page_data(analyzer)
    assert "asio" in out
    assert out["asio"]["internal_dependents_data"]["table_data"][0]["name"] == "dep"
    assert "over_view" in out["asio"]


def test_collect_commit_info_by_library_empty_iterator():
    analyzer = MagicMock()
    analyzer.library_info = [{"name": "algo"}]
    v = MagicMock()
    v.version = "boost-1.81.0"
    analyzer.version_info = [v]

    qs = MagicMock()
    qs.iterator.return_value = []
    mgr = MagicMock()
    mgr.select_related.return_value.filter.return_value.exclude.return_value = qs

    with patch(
        "boost_library_usage_dashboard.analyzer_libraries.GitCommitFileChange.objects",
        mgr,
    ):
        out = collect_commit_info_by_library(analyzer)

    assert "algo" in out
    assert out["algo"]["boost-1.81.0"]["count"] == 0
    assert out["algo"]["boost-1.81.0"]["persons"] == {}
