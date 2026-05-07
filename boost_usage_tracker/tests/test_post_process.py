"""Tests for boost_usage_tracker.post_process header resolution."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from model_bakery import baker

from core.operations.github_ops.client import (
    ConnectionException,
    RateLimitException,
)
from boost_library_tracker import services as boost_library_services
from boost_usage_tracker.boost_searcher import FileSearchResult
from boost_usage_tracker.models import BoostUsage
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


@pytest.mark.django_db
def test_process_single_repo_propagates_rate_limit_exception():
    rr = RepoSearchResult(full_name="owner/repo-rl")

    def ensure(*_a, **_k):
        raise RateLimitException("slow down")

    with pytest.raises(RateLimitException):
        process_single_repo(
            MagicMock(),
            rr,
            [],
            datetime.now(timezone.utc),
            ensure,
        )


@pytest.mark.django_db
def test_process_single_repo_no_file_results_skips_version_detection(
    external_github_repository,
):
    rr = RepoSearchResult(full_name=_repo_full_name(external_github_repository))

    def ensure(_c, _r):
        return external_github_repository

    with patch(
        "boost_usage_tracker.post_process.detect_boost_version_in_repo"
    ) as m_det:
        stats = process_single_repo(
            MagicMock(),
            rr,
            [],
            datetime.now(timezone.utc),
            ensure,
        )
    m_det.assert_not_called()
    assert stats["boost_used"] is False


def _repo_full_name(github_repository):
    return f"{github_repository.owner_account.username}/{github_repository.repo_name}"


@pytest.mark.django_db
def test_process_single_repo_bulk_usage_and_boost_used(
    external_github_repository, ext_repo, github_file, boost_library
):
    """Non-empty file results: detect version, resolve header, bulk create usage."""
    github_file.filename = "boost/asio.hpp"
    github_file.save(update_fields=["filename"])
    boost_hdr, _ = boost_library_services.get_or_create_boost_file(
        github_file, boost_library
    )
    rr = RepoSearchResult(full_name=_repo_full_name(external_github_repository))
    src_file = baker.make(
        "github_activity_tracker.GitHubFile",
        repo=external_github_repository,
        filename="app/main.cpp",
    )
    fr = FileSearchResult(
        repo_full_name=rr.full_name,
        file_path=src_file.filename,
        content="#include <boost/asio.hpp>\n",
        commit_date=datetime(2025, 7, 1, tzinfo=timezone.utc),
    )

    def ensure(_c, _r):
        return external_github_repository

    with patch(
        "boost_usage_tracker.post_process.detect_boost_version_in_repo",
        return_value=(True, "1.85.0"),
    ):
        stats = process_single_repo(
            MagicMock(),
            rr,
            [fr],
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            ensure,
        )

    assert stats["boost_used"] is True
    assert stats["usages_created"] >= 1
    usage = BoostUsage.objects.filter(
        repo=ext_repo, boost_header=boost_hdr, file_path=src_file
    ).first()
    assert usage is not None


@pytest.mark.django_db
def test_process_single_repo_skips_stale_file_and_uses_boost_headers_fallback(
    external_github_repository, ext_repo, github_file, boost_library
):
    """Skip already-processed files; empty extract uses file_result.boost_headers."""
    github_file.filename = "boost/thread.hpp"
    github_file.save(update_fields=["filename"])
    boost_hdr, _ = boost_library_services.get_or_create_boost_file(
        github_file, boost_library
    )
    rr = RepoSearchResult(full_name=_repo_full_name(external_github_repository))
    stale = baker.make(
        "github_activity_tracker.GitHubFile",
        repo=external_github_repository,
        filename="old.cpp",
    )
    fresh = baker.make(
        "github_activity_tracker.GitHubFile",
        repo=external_github_repository,
        filename="new.cpp",
    )
    cutoff = datetime(2025, 6, 15, tzinfo=timezone.utc)
    stale_fr = FileSearchResult(
        repo_full_name=rr.full_name,
        file_path=stale.filename,
        content="",
        commit_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        boost_headers=[],
    )
    fresh_fr = FileSearchResult(
        repo_full_name=rr.full_name,
        file_path=fresh.filename,
        content="",
        commit_date=datetime(2025, 7, 1, tzinfo=timezone.utc),
        boost_headers=["boost/thread.hpp"],
    )

    def ensure(_c, _r):
        return external_github_repository

    with patch(
        "boost_usage_tracker.post_process.detect_boost_version_in_repo",
        return_value=(False, ""),
    ):
        with patch(
            "boost_usage_tracker.post_process.create_or_update_github_file"
        ) as m_file:
            m_file.side_effect = [
                (stale, False),
                (fresh, True),
            ]
            stats = process_single_repo(
                MagicMock(),
                rr,
                [stale_fr, fresh_fr],
                cutoff,
                ensure,
            )

    assert stats["usages_created"] >= 1
    assert BoostUsage.objects.filter(
        repo=ext_repo, boost_header=boost_hdr, file_path=fresh
    ).exists()


@pytest.mark.django_db
def test_process_single_repo_missing_header_records_tmp(
    ext_repo, external_github_repository
):
    rr = RepoSearchResult(full_name=_repo_full_name(external_github_repository))
    gf = baker.make(
        "github_activity_tracker.GitHubFile",
        repo=external_github_repository,
        filename="x.cpp",
    )
    fr = FileSearchResult(
        repo_full_name=rr.full_name,
        file_path=gf.filename,
        content="#include <boost/does/not/exist_ever.hpp>\n",
        commit_date=datetime(2025, 8, 1, tzinfo=timezone.utc),
    )

    def ensure(_c, _r):
        return external_github_repository

    with patch(
        "boost_usage_tracker.post_process.detect_boost_version_in_repo",
        return_value=(False, ""),
    ):
        stats = process_single_repo(
            MagicMock(),
            rr,
            [fr],
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            ensure,
        )

    assert stats["missing_header_recorded"] >= 1
    assert BoostUsage.objects.filter(repo=ext_repo, boost_header__isnull=True).exists()


@pytest.mark.django_db
def test_process_single_repo_marks_stale_usages_excepted(
    external_github_repository, ext_repo, github_file, boost_library
):
    github_file.filename = "boost/lambda.hpp"
    github_file.save(update_fields=["filename"])
    boost_hdr, _ = boost_library_services.get_or_create_boost_file(
        github_file, boost_library
    )
    old_src = baker.make(
        "github_activity_tracker.GitHubFile",
        repo=external_github_repository,
        filename="legacy.cpp",
    )
    baker.make(
        BoostUsage,
        repo=ext_repo,
        boost_header=boost_hdr,
        file_path=old_src,
        last_commit_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    rr = RepoSearchResult(full_name=_repo_full_name(external_github_repository))
    new_src = baker.make(
        "github_activity_tracker.GitHubFile",
        repo=external_github_repository,
        filename="current.cpp",
    )
    fr = FileSearchResult(
        repo_full_name=rr.full_name,
        file_path=new_src.filename,
        content="#include <boost/lambda.hpp>\n",
        commit_date=datetime(2025, 9, 1, tzinfo=timezone.utc),
    )

    def ensure(_c, _r):
        return external_github_repository

    with patch(
        "boost_usage_tracker.post_process.detect_boost_version_in_repo",
        return_value=(False, ""),
    ):
        stats = process_single_repo(
            MagicMock(),
            rr,
            [fr],
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            ensure,
        )

    assert stats["usages_excepted"] >= 1
    old_usage = BoostUsage.objects.get(repo=ext_repo, file_path=old_src)
    assert old_usage.excepted_at is not None
