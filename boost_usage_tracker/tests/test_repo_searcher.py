"""Unit tests for boost_usage_tracker.repo_searcher."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from boost_usage_tracker.repo_searcher import (
    CREATION_INTERVAL_DAYS,
    _extract_repo_metadata,
    _process_date_range,
    _search_repos_by_query,
    generate_date_ranges,
    search_repos_with_date_splitting,
)


def test_extract_repo_metadata_license_variants():
    base = {
        "full_name": "acme/cppproj",
        "stargazers_count": 12,
        "description": "desc",
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2021-01-01T00:00:00Z",
        "pushed_at": "2022-01-01T00:00:00Z",
        "forks_count": 3,
    }
    r = _extract_repo_metadata({**base, "license": {"spdx_id": "MIT"}})
    assert r.full_name == "acme/cppproj"
    assert r.license_spdx == "MIT"

    r2 = _extract_repo_metadata({**base, "license": {"key": "apache-2.0"}})
    assert r2.license_spdx == "apache-2.0"

    r3 = _extract_repo_metadata({**base, "license": {"name": "BSD"}})
    assert r3.license_spdx == "BSD"

    r4 = _extract_repo_metadata({**base, "license": "broken"})
    assert r4.license_spdx == ""


def test_extract_repo_metadata_skips_empty_full_name():
    r = _extract_repo_metadata({"full_name": "", "stargazers_count": 1})
    assert r.full_name == ""


def test_generate_date_ranges_pushed_one_day_steps():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 3, tzinfo=timezone.utc)
    ranges = generate_date_ranges(start, end, date_field="pushed")
    assert len(ranges) == 3
    assert ranges[0][0].date() == start.date()


def test_generate_date_ranges_created_uses_interval():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=CREATION_INTERVAL_DAYS)
    ranges = generate_date_ranges(start, end, date_field="created")
    assert CREATION_INTERVAL_DAYS >= 1
    assert len(ranges) >= 1


def test_search_repos_by_query_pagination_and_empty():
    client = MagicMock()
    client.rest_request.return_value = {"items": []}
    assert _search_repos_by_query(client, "language:c++") == []


def test_search_repos_by_query_collects_pages():
    client = MagicMock()

    def rest_side_effect(_path, params=None):
        page = params.get("page", 1)
        if page == 1:
            return {
                "items": [
                    {"full_name": "a/a", "license": None},
                    {"full_name": "", "license": None},
                ],
            }
        return {"items": []}

    client.rest_request.side_effect = rest_side_effect
    out = _search_repos_by_query(client, "q")
    assert len(out) == 1
    assert out[0].full_name == "a/a"


def test_search_repos_by_query_request_failure():
    client = MagicMock()
    client.rest_request.side_effect = RuntimeError("network")
    assert _search_repos_by_query(client, "q") == []


def test_process_date_range_probe_fails():
    client = MagicMock()
    client.rest_request.side_effect = RuntimeError("fail")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert (
        _process_date_range(
            client,
            (start, start),
            date_field="pushed",
        )
        == []
    )


def test_process_date_range_under_limit():
    client = MagicMock()

    def side_effect(_path, params=None):
        per_page = params.get("per_page", 100)
        if per_page == 1:
            return {"total_count": 3, "items": [{}]}
        return {"items": [{"full_name": "o/r", "license": None, "stargazers_count": 5}]}

    client.rest_request.side_effect = side_effect
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 2, tzinfo=timezone.utc)
    repos = _process_date_range(client, (start, end), date_field="pushed")
    assert len(repos) == 1
    assert repos[0].full_name == "o/r"


def test_search_repos_with_date_splitting_dedupes():
    client = MagicMock()

    def side_effect(_path, params=None):
        if params.get("per_page") == 1:
            return {"total_count": 1}
        return {"items": [{"full_name": "dup/names", "license": None}]}

    client.rest_request.side_effect = side_effect
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = search_repos_with_date_splitting(client, start, end, date_field="pushed")
    assert len(out) == 1
