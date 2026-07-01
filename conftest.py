"""
Root conftest: register app-level fixture modules and optional session/global fixtures.
"""

import os

import pytest

# Exclude benchmarks/ from default test collection (keeps CI and local pytest fast).
# Run benchmarks with: RUN_BENCHMARKS=1 uv run pytest benchmarks/ -m benchmark ...
collect_ignore = [] if os.environ.get("RUN_BENCHMARKS") == "1" else ["benchmarks"]


def _patch_django_context_copy_py314():
    """Fix Django BaseContext.__copy__ on Python 3.14 (copy(super()) is broken there)."""
    import sys

    if sys.version_info >= (3, 14):  # pragma: no cover
        from django.template.context import BaseContext

        def __copy__(self):
            duplicate = object.__new__(type(self))
            duplicate.__dict__ = self.__dict__.copy()
            duplicate.dicts = self.dicts[:]
            return duplicate

        BaseContext.__copy__ = __copy__


def pytest_configure(config):  # noqa: F841 (pytest hook; name must match spec)
    _patch_django_context_copy_py314()


# Load app-level fixture modules so fixtures from each app are available everywhere.
# Subset-schema settings omit peer apps (and cppa_user_tracker); skip their fixture plugins.
_settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
_subset_schema_settings = _settings_module.endswith(
    "test_settings_subset_boost_mailing_list"
)

if _subset_schema_settings:
    pytest_plugins: list[str] = []
else:
    pytest_plugins = [
        "core.tests.failure_classification_helpers",
        "cppa_user_tracker.tests.fixtures",
        "core.tests.github_ops.fixtures",
        "github_activity_tracker.tests.fixtures",
        "boost_library_tracker.tests.fixtures",
        "boost_library_docs_tracker.tests.fixtures",
        "cppa_pinecone_sync.tests.fixtures",
        "cppa_slack_tracker.tests.fixtures",
        "boost_library_usage_dashboard.tests.fixtures",
        "boost_usage_tracker.tests.fixtures",
        "boost_mailing_list_tracker.tests.fixtures",
        "boost_collector_runner.tests.fixtures",
    ]


@pytest.fixture(scope="session")
def test_workspace_dir():
    """Session-scoped path to test workspace (for tests that need a real path)."""
    from pathlib import Path
    from django.conf import settings

    return getattr(
        settings,
        "WORKSPACE_DIR",
        Path(__file__).resolve().parent / ".test_artifacts" / "workspace",
    )
