"""Tests for boost_library_tracker Pinecone preprocessor wrappers."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_issue_preprocess_for_pinecone_delegates(settings):
    settings.BOOST_GITHUB_OWNER = "boostorg"
    ts = datetime.now(timezone.utc)
    with patch(
        "boost_library_tracker.preprocessors.issue_preprocessor.preprocess_all_issues",
    ) as mock_issues:
        mock_issues.return_value = ([{"id": "doc"}], False)
        from boost_library_tracker.preprocessors.issue_preprocessor import (
            preprocess_for_pinecone,
        )

        docs, chunked = preprocess_for_pinecone(["f1"], ts)
    mock_issues.assert_called_once_with("boostorg", ["f1"], ts)
    assert len(docs) == 1
    assert chunked is False


@pytest.mark.django_db
def test_pr_preprocess_for_pinecone_delegates(settings):
    settings.BOOST_GITHUB_OWNER = "boostorg"
    _ = datetime.now(timezone.utc)
    with patch(
        "boost_library_tracker.preprocessors.pr_preprocessor.preprocess_all_prs",
    ) as mock_prs:
        mock_prs.return_value = ([], False)
        from boost_library_tracker.preprocessors.pr_preprocessor import (
            preprocess_for_pinecone as pr_preprocess,
        )

        docs, chunked = pr_preprocess([], None)
    mock_prs.assert_called_once_with("boostorg", [], None)
    assert docs == []
    assert chunked is False
