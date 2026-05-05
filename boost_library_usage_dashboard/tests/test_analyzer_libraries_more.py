"""Extra tests for boost_library_usage_dashboard.analyzer_libraries."""

from unittest.mock import MagicMock, patch

import pytest

from boost_library_usage_dashboard.analyzer_libraries import (
    collect_dependents_data,
    find_all_transitive_dependencies,
)


@pytest.mark.django_db
def test_collect_dependents_data_empty_dependencies():
    analyzer = MagicMock()
    v = MagicMock()
    v.id = 100
    v.version = "boost-1.50.0"
    analyzer.version_info = [v]
    analyzer.library_info = [{"id": 1, "name": "Alpha"}]
    with patch(
        "boost_library_usage_dashboard.analyzer_libraries.BoostDependency.objects.values",
        return_value=[],
    ):
        out = collect_dependents_data(analyzer)
    assert 1 in out
    assert out[1]["table_data"] == []


def test_find_all_transitive_dependencies_simple_chain():
    graph = {
        1: {10: [2]},
        2: {10: [3]},
        3: {10: []},
    }
    got = find_all_transitive_dependencies(1, 10, graph)
    assert 2 in got and 3 in got
