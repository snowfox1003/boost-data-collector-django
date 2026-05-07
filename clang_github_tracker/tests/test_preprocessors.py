"""Tests for DB-driven clang preprocessors."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone

from clang_github_tracker.models import ClangGithubIssueItem
from clang_github_tracker.preprocessors import issue_preprocessor, pr_preprocessor


@pytest.mark.django_db
@patch("clang_github_tracker.preprocessors.issue_preprocessor.build_issue_document")
def test_issue_preprocessor_db_and_failed_ids(mock_build, tmp_path, settings):
    settings.CLANG_GITHUB_OWNER = "llvm"
    settings.CLANG_GITHUB_REPO = "llvm-project"
    mock_build.return_value = {
        "content": "body",
        "metadata": {"doc_id": "u", "ids": "x"},
    }

    p10 = tmp_path / "10.json"
    p10.write_text("{}", encoding="utf-8")
    p99 = tmp_path / "99.json"
    p99.write_text("{}", encoding="utf-8")

    ClangGithubIssueItem.objects.create(
        number=10,
        is_pull_request=False,
        github_updated_at=timezone.now(),
    )
    final = timezone.now() - timedelta(hours=1)

    def _issue_path(_owner, _repo, n):
        return {10: p10, 99: p99}.get(n, tmp_path / f"missing_{n}.json")

    with patch(
        "clang_github_tracker.preprocessors.issue_preprocessor.get_raw_source_issue_path",
        side_effect=_issue_path,
    ):
        docs, chunked = issue_preprocessor.preprocess_for_pinecone(
            ["llvm-project:issue:99"], final
        )
    assert chunked is False
    # DB watermark picks #10; failed_ids must parse llvm-project:issue:99 and add #99.
    assert mock_build.call_count == 2
    assert len(docs) == 2


@pytest.mark.django_db
@patch("clang_github_tracker.preprocessors.issue_preprocessor.build_issue_document")
def test_issue_preprocessor_all_rows_when_final_sync_none(
    mock_build, tmp_path, settings
):
    settings.CLANG_GITHUB_OWNER = "llvm"
    settings.CLANG_GITHUB_REPO = "llvm-project"
    mock_build.return_value = None
    p5 = tmp_path / "5.json"
    p5.write_text("{}", encoding="utf-8")
    ClangGithubIssueItem.objects.create(
        number=5,
        is_pull_request=False,
        github_updated_at=timezone.now(),
    )
    with patch(
        "clang_github_tracker.preprocessors.issue_preprocessor.get_raw_source_issue_path",
        return_value=p5,
    ):
        docs, _ = issue_preprocessor.preprocess_for_pinecone([], None)
    assert mock_build.call_count == 1
    assert docs == []


@pytest.mark.django_db
@patch("clang_github_tracker.preprocessors.pr_preprocessor.build_pr_document")
def test_pr_preprocessor_failed_id_parsing(mock_build, tmp_path, settings):
    settings.CLANG_GITHUB_OWNER = "llvm"
    settings.CLANG_GITHUB_REPO = "llvm-project"
    mock_build.return_value = {"content": "p", "metadata": {"doc_id": "u", "ids": "y"}}
    p7 = tmp_path / "7.json"
    p7.write_text("{}", encoding="utf-8")
    with patch(
        "clang_github_tracker.preprocessors.pr_preprocessor.get_raw_source_pr_path",
        return_value=p7,
    ):
        docs, chunked = pr_preprocessor.preprocess_for_pinecone(
            ["llvm-project:pr:7"], timezone.now()
        )
    assert chunked is False
    assert mock_build.call_count == 1
    assert len(docs) == 1


@pytest.mark.django_db
@patch("clang_github_tracker.preprocessors.issue_preprocessor.build_issue_document")
def test_issue_preprocessor_naive_final_sync_made_aware(mock_build, tmp_path, settings):
    settings.CLANG_GITHUB_OWNER = "llvm"
    settings.CLANG_GITHUB_REPO = "llvm-project"
    mock_build.return_value = {"content": "x", "metadata": {}}
    p = tmp_path / "1.json"
    p.write_text("{}", encoding="utf-8")
    ClangGithubIssueItem.objects.create(
        number=1,
        is_pull_request=False,
        github_updated_at=timezone.now(),
    )
    naive = datetime(2020, 1, 1, 0, 0, 0)
    with patch(
        "clang_github_tracker.preprocessors.issue_preprocessor.get_raw_source_issue_path",
        return_value=p,
    ):
        issue_preprocessor.preprocess_for_pinecone([], naive)
    assert mock_build.call_count >= 1


@pytest.mark.django_db
@patch("clang_github_tracker.preprocessors.issue_preprocessor.build_issue_document")
def test_issue_preprocessor_skips_missing_raw_and_bad_json(
    mock_build, tmp_path, settings
):
    settings.CLANG_GITHUB_OWNER = "llvm"
    settings.CLANG_GITHUB_REPO = "llvm-project"
    ClangGithubIssueItem.objects.create(
        number=1,
        is_pull_request=False,
        github_updated_at=timezone.now(),
    )
    bad = Path("/nonexistent/issue_1.json")
    with patch(
        "clang_github_tracker.preprocessors.issue_preprocessor.get_raw_source_issue_path",
        return_value=bad,
    ):
        docs, _ = issue_preprocessor.preprocess_for_pinecone([], None)
    assert docs == [] and mock_build.call_count == 0

    p = tmp_path / "1.json"
    p.write_text("not-json", encoding="utf-8")
    with patch(
        "clang_github_tracker.preprocessors.issue_preprocessor.get_raw_source_issue_path",
        return_value=p,
    ):
        docs2, _ = issue_preprocessor.preprocess_for_pinecone([], None)
    assert docs2 == [] and mock_build.call_count == 0


@pytest.mark.django_db
@patch("clang_github_tracker.preprocessors.pr_preprocessor.build_pr_document")
def test_pr_preprocessor_naive_final_sync_and_bad_json(mock_build, tmp_path, settings):
    settings.CLANG_GITHUB_OWNER = "llvm"
    settings.CLANG_GITHUB_REPO = "llvm-project"
    mock_build.return_value = {"content": "p", "metadata": {}}
    p = tmp_path / "2.json"
    p.write_text("{}", encoding="utf-8")
    ClangGithubIssueItem.objects.create(
        number=2,
        is_pull_request=True,
        github_updated_at=timezone.now(),
    )
    naive = datetime(2020, 1, 1, 0, 0, 0)
    with patch(
        "clang_github_tracker.preprocessors.pr_preprocessor.get_raw_source_pr_path",
        return_value=p,
    ):
        pr_preprocessor.preprocess_for_pinecone([], naive)
    assert mock_build.call_count >= 1

    p.write_text("{", encoding="utf-8")
    calls_before = mock_build.call_count
    with patch(
        "clang_github_tracker.preprocessors.pr_preprocessor.get_raw_source_pr_path",
        return_value=p,
    ):
        docs, _ = pr_preprocessor.preprocess_for_pinecone([], None)
    assert docs == []
    assert mock_build.call_count == calls_before
