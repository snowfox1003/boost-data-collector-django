"""Tests for github_activity_tracker.api_schemas."""

import pytest

from github_activity_tracker.api_schemas import (
    GitHubApiValidationError,
    parse_commit,
    parse_issue_bundle,
    parse_pr_bundle,
)


def test_parse_issue_bundle_flat():
    bundle = parse_issue_bundle(
        {
            "number": 1,
            "id": 100,
            "title": "t",
            "user": {"id": 1, "login": "u"},
            "comments": [],
        }
    )
    assert bundle.issue.number == 1
    assert bundle.issue.id == 100


def test_parse_issue_bundle_nested():
    bundle = parse_issue_bundle(
        {
            "issue_info": {"number": 2, "id": 200, "user": {"id": 2, "login": "x"}},
            "comments": [{"id": 1, "body": "c", "user": {"id": 2, "login": "x"}}],
        }
    )
    assert bundle.issue.number == 2
    assert len(bundle.issue.comments) == 1


def test_parse_issue_bundle_invalid_payload_raises():
    with pytest.raises(GitHubApiValidationError):
        parse_issue_bundle("not-a-dict")  # type: ignore[arg-type]


def test_parse_issue_bundle_missing_number_raises():
    with pytest.raises(GitHubApiValidationError):
        parse_issue_bundle({"id": 100, "title": "t", "comments": []})


def test_parse_issue_bundle_accepts_null_state_reason_and_title():
    bundle = parse_issue_bundle(
        {
            "number": 1,
            "id": 100,
            "title": None,
            "state_reason": None,
            "user": {"id": 1, "login": "u"},
            "comments": [],
        }
    )
    assert bundle.issue.title is None
    assert bundle.issue.state_reason is None


def test_parse_pr_bundle():
    bundle = parse_pr_bundle(
        {
            "number": 3,
            "id": 300,
            "user": {"id": 3, "login": "p"},
            "head": {"sha": "abc"},
            "base": {"sha": "def"},
            "comments": [],
            "reviews": [],
        }
    )
    assert bundle.pr.number == 3


def test_parse_pr_bundle_missing_number_raises():
    with pytest.raises(GitHubApiValidationError):
        parse_pr_bundle(
            {
                "id": 300,
                "user": {"id": 3, "login": "p"},
                "comments": [],
                "reviews": [],
            }
        )


def test_parse_pr_bundle_accepts_null_title_head_base_and_review_body():
    bundle = parse_pr_bundle(
        {
            "number": 3,
            "id": 300,
            "title": None,
            "head": None,
            "base": None,
            "user": {"id": 3, "login": "p"},
            "comments": [{"id": 1, "body": None, "user": {"id": 3, "login": "p"}}],
            "reviews": [{"id": 2, "body": None, "user": {"id": 4, "login": "r"}}],
        }
    )
    assert bundle.pr.title is None
    assert bundle.pr.head is None
    assert bundle.pr.base is None
    assert bundle.pr.comments[0].body is None
    assert bundle.pr.reviews[0].body is None


def test_parse_commit_requires_sha():
    commit = parse_commit(
        {
            "sha": "abc123",
            "commit": {"message": "m", "author": {"date": "2024-01-01T00:00:00Z"}},
        }
    )
    assert commit.sha == "abc123"


def test_parse_commit_missing_sha_raises():
    with pytest.raises(GitHubApiValidationError):
        parse_commit({"commit": {"message": "m"}})
