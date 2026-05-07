"""Direct unit tests for boost_library_usage_dashboard.analyzer_metrics."""

# Tests intentionally exercise ``_float_from_env`` (module-private helper).
# pylint: disable=protected-access

from __future__ import annotations

import os
from unittest.mock import patch

import datetime as dt_module

import pytest

from boost_library_usage_dashboard import analyzer_metrics as metrics


class _FixedNowDatetime:
    """Stand-in for ``datetime`` class with a controlled ``now()``."""

    fixed_year: int = 2030

    @staticmethod
    def now(_tz=None):
        return dt_module.datetime(_FixedNowDatetime.fixed_year, 1, 1)


def test_float_from_env_empty_uses_default():
    key = "BOOST_DASHBOARD_TEST_FLOAT_METRICS_" + str(
        id(test_float_from_env_empty_uses_default)
    )
    os.environ.pop(key, None)
    assert metrics._float_from_env(key, 0.42) == pytest.approx(0.42)


def test_float_from_env_valid_number():
    key = "BOOST_DASHBOARD_TEST_FLOAT_METRICS_" + str(
        id(test_float_from_env_valid_number)
    )
    with patch.dict(os.environ, {key: " 2.5 "}):
        assert metrics._float_from_env(key, 1.0) == pytest.approx(2.5)


def test_float_from_env_invalid_falls_back():
    key = "BOOST_DASHBOARD_TEST_FLOAT_METRICS_" + str(
        id(test_float_from_env_invalid_falls_back)
    )
    with patch.dict(os.environ, {key: "not-a-float"}):
        assert metrics._float_from_env(key, 0.25) == pytest.approx(0.25)


def test_calculate_trend_metrics_empty_year_data():
    out = metrics.calculate_trend_metrics([], recent_year_threshold=2020)
    assert out["total_usage"] == 0
    assert out["activity_score"] == -10.0


def test_calculate_trend_metrics_zero_total_usage():
    out = metrics.calculate_trend_metrics(
        [(2022, {"created_count": 0, "last_commit_count": 0})],
        recent_year_threshold=2020,
    )
    assert out["activity_score"] == -10.0


def test_calculate_trend_metrics_uses_fallback_when_only_current_year():
    fixed_year = 2030
    year_data = [
        (fixed_year, {"created_count": 5, "last_commit_count": 0}),
        (fixed_year, {"created_count": 5, "last_commit_count": 0}),
    ]
    _FixedNowDatetime.fixed_year = fixed_year
    with patch(
        "boost_library_usage_dashboard.analyzer_metrics.datetime", _FixedNowDatetime
    ):
        out = metrics.calculate_trend_metrics(
            year_data, recent_year_threshold=fixed_year - 5
        )
    assert out["total_usage"] == 10
    assert isinstance(out["activity_score"], float)


def test_calculate_trend_metrics_zero_denom_trend_skipped():
    """Duplicate calendar years => x_values tied => linear regression denominator zero."""
    fixed_now_year = 2026
    _FixedNowDatetime.fixed_year = fixed_now_year
    year_data = [
        (2020, {"created_count": 3, "last_commit_count": 0}),
        (2020, {"created_count": 2, "last_commit_count": 0}),
    ]
    with patch(
        "boost_library_usage_dashboard.analyzer_metrics.datetime", _FixedNowDatetime
    ):
        out = metrics.calculate_trend_metrics(year_data, recent_year_threshold=2019)
    assert out["total_usage"] == 5
    assert isinstance(out["activity_score"], float)


def test_calculate_trend_metrics_momentum_requires_two_points():
    fixed_now_year = 2027
    _FixedNowDatetime.fixed_year = fixed_now_year
    with patch(
        "boost_library_usage_dashboard.analyzer_metrics.datetime", _FixedNowDatetime
    ):
        single = metrics.calculate_trend_metrics(
            [(2024, {"created_count": 10, "last_commit_count": 0})],
            recent_year_threshold=2020,
        )
        multi = metrics.calculate_trend_metrics(
            [
                (2023, {"created_count": 2, "last_commit_count": 0}),
                (2024, {"created_count": 8, "last_commit_count": 0}),
            ],
            recent_year_threshold=2020,
        )
    assert single["total_usage"] == 10
    assert multi["total_usage"] == 10
    assert isinstance(multi["activity_score"], float)


@pytest.mark.django_db
def test_calculate_library_metrics_by_repository_empty_db():
    """No BoostUsage rows => empty metrics dict."""

    class FakeAnalyzer:
        stars_min_threshold = 10

    assert metrics.calculate_library_metrics_by_repository(FakeAnalyzer()) == {}
