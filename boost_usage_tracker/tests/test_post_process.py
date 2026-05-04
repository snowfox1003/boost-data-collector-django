"""Tests for boost_usage_tracker.post_process header resolution."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.operations.github_ops.client import ConnectionException
from boost_library_tracker import services as boost_library_services
from boost_usage_tracker.post_process import (
    _resolve_boost_header,
    _resolve_boost_headers_bulk,
    process_single_repo,
)
from boost_usage_tracker.repo_searcher import RepoSearchResult


@pytest.mark.django_db
def test_resolve_boost_headers_bulk_empty():
    assert _resolve_boost_headers_bulk(set()) == {}


@pytest.mark.django_db
def test_resolve_boost_headers_bulk_exact_and_suffix(github_file, boost_library):
    """Exact filename match then suffix fallback."""
    github_file.filename = "boost/detail/foo.hpp"
    github_file.save(update_fields=["filename"])
    bf, _ = boost_library_services.get_or_create_boost_file(github_file, boost_library)

    exact = {github_file.filename}
    resolved = _resolve_boost_headers_bulk(exact)
    assert resolved[github_file.filename].pk == bf.pk

    partial = {"detail/foo.hpp"}
    resolved2 = _resolve_boost_headers_bulk(partial)
    assert resolved2["detail/foo.hpp"].pk == bf.pk


@pytest.mark.django_db
def test_resolve_boost_header_no_match():
    assert _resolve_boost_header("boost/does/not/exist.hpp") is None


@pytest.mark.django_db
def test_process_single_repo_propagates_connection_exception():
    rr = RepoSearchResult(full_name="owner/repo")

    def ensure(*_a, **_k):
        raise ConnectionException("abort")

    with pytest.raises(ConnectionException):
        process_single_repo(
            MagicMock(),
            rr,
            [],
            datetime.now(timezone.utc),
            ensure,
        )


@pytest.mark.django_db
def test_process_single_repo_logs_generic_errors(caplog):
    rr = RepoSearchResult(full_name="owner/repo2")

    def ensure(*_a, **_k):
        raise RuntimeError("boom")

    import logging

    caplog.set_level(logging.WARNING)
    stats = process_single_repo(
        MagicMock(),
        rr,
        [],
        datetime.now(timezone.utc),
        ensure,
    )
    assert stats["usages_created"] == 0
    assert any("Failed post-processing" in r.message for r in caplog.records)
