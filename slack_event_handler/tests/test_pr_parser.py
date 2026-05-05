"""Tests for slack_event_handler.utils.pr_parser."""

from slack_event_handler.utils.pr_parser import extract_pr_urls


def test_extract_pr_urls_empty_text():
    valid, invalid = extract_pr_urls("")
    assert valid == [] and invalid == []


def test_extract_pr_urls_no_allowed_org_all_valid():
    text = "See https://github.com/foo/bar/pull/1 and https://github.com/Org2/x/pull/2"
    valid, invalid = extract_pr_urls(text)
    assert len(valid) == 2
    assert invalid == []
    assert valid[0]["owner"] == "foo"
    assert valid[0]["pull_number"] == 1


def test_extract_pr_urls_with_allowed_org_splits():
    text = "https://github.com/boostorg/beast/pull/99 https://github.com/other/x/pull/1"
    valid, invalid = extract_pr_urls(text, allowed_org="boostorg")
    assert len(valid) == 1
    assert valid[0]["repo"] == "beast"
    assert len(invalid) == 1
    assert invalid[0]["owner"] == "other"


def test_extract_pr_urls_allowed_org_case_insensitive():
    url = "https://github.com/MyOrg/Repo/pull/3"
    valid, invalid = extract_pr_urls(url, allowed_org="MYORG")
    assert len(valid) == 1 and invalid == []
