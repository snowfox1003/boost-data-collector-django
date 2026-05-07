"""Tests for GitHubAPIClient pagination helpers, raw GET, and validation."""

from unittest.mock import MagicMock

import pytest

from core.operations.github_ops.client import GitHubAPIClient


def test_parse_link_next_extracts_url():
    hdr = '<https://api.github.com/repos/o/r/issues?page=2>; rel="next"'
    assert (
        GitHubAPIClient._parse_link_next(hdr)
        == "https://api.github.com/repos/o/r/issues?page=2"
    )


def test_parse_link_next_none_when_missing():
    assert GitHubAPIClient._parse_link_next(None) is None
    assert GitHubAPIClient._parse_link_next('<http://x>; rel="prev"') is None


def test_parse_link_rels_builds_dict():
    hdr = (
        '<https://api.github.com/a?page=2>; rel="next", '
        '<https://api.github.com/a?page=10>; rel="last"'
    )
    d = GitHubAPIClient._parse_link_rels(hdr)
    assert d["next"].endswith("page=2")
    assert d["last"].endswith("page=10")


def test_parse_link_rels_empty_header():
    assert GitHubAPIClient._parse_link_rels("") == {}
    assert GitHubAPIClient._parse_link_rels(None) == {}


def test_validate_rest_pagination_url_rejects_non_https():
    c = GitHubAPIClient("t")
    with pytest.raises(ValueError, match="only https"):
        c._validate_rest_pagination_url("http://api.github.com/repos/x")


def test_validate_rest_pagination_url_rejects_wrong_host():
    c = GitHubAPIClient("t")
    with pytest.raises(ValueError, match="outside"):
        c._validate_rest_pagination_url("https://evil.example/page")


def test_validate_rest_pagination_url_rejects_relative():
    c = GitHubAPIClient("t")
    with pytest.raises(ValueError, match="missing host"):
        c._validate_rest_pagination_url("/repos/foo")


def test_rest_request_returns_empty_when_rest_get_returns_none():
    c = GitHubAPIClient("t")
    c._rest_get = MagicMock(return_value=(None, "etag"))
    assert c.rest_request("/repos/o/r/issues") == {}


def test_rest_raw_request_returns_none_when_no_response():
    c = GitHubAPIClient("t")
    c._do_request = MagicMock(return_value=None)
    assert c.rest_raw_request("https://api.github.com/raw") is None


def test_rest_request_with_link_empty_when_no_response():
    c = GitHubAPIClient("t")
    c._rest_get = MagicMock(return_value=(None, None))
    data, next_url = c.rest_request_with_link("/repos/o/r/issues")
    assert data == {}
    assert next_url is None


def test_rest_request_with_all_links_empty_when_no_response():
    c = GitHubAPIClient("t")
    c._rest_get = MagicMock(return_value=(None, None))
    data, links = c.rest_request_with_all_links("/repos/o/r/issues")
    assert data == {}
    assert links == {}


def test_rest_request_conditional_with_link_304_branch():
    c = GitHubAPIClient("t")
    c._rest_get = MagicMock(return_value=(None, 'W/"e"'))
    data, etag, next_url = c.rest_request_conditional_with_link(
        "/repos/o/r/issues", etag='W/"e"'
    )
    assert data is None
    assert etag == 'W/"e"'
    assert next_url is None


def test_rest_request_conditional_with_all_links_304_branch():
    c = GitHubAPIClient("t")
    c._rest_get = MagicMock(return_value=(None, 'W/"x"'))
    data, etag, links = c.rest_request_conditional_with_all_links(
        "/repos/o/r/issues", etag='W/"x"'
    )
    assert data is None
    assert links == {}
