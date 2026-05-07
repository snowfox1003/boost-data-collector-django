"""Tests for GitHubAPIClient.get_submodules, list_contents, get_tag_sha, get_tag_published_at."""

import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import requests

from core.operations.github_ops.client import GitHubAPIClient


def test_list_contents_root_and_nested():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(side_effect=[[{"name": "a"}], {"name": "README"}])
    assert c.list_contents("o", "r") == [{"name": "a"}]
    assert c.list_contents("o", "r", path="src", ref="main") == {"name": "README"}
    assert "/contents/src" in c.rest_request.call_args_list[1][0][0]


def test_get_submodules_from_api_file():
    c = GitHubAPIClient("t")
    raw = b'[submodule "x"]\npath = x\nurl = ../x.git\n'
    b64 = base64.b64encode(raw).decode("ascii")
    c.rest_request = MagicMock(
        return_value={"type": "file", "encoding": "base64", "content": b64}
    )
    out = c.get_submodules("boostorg", "boost")
    assert len(out) == 1


def test_get_submodules_api_returns_list():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(return_value=[{"name": "wrong"}])
    assert c.get_submodules("o", "r") == []


def test_get_submodules_api_decode_error_returns_empty():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(
        return_value={"type": "file", "encoding": "base64", "content": "!!!"}
    )
    assert c.get_submodules("o", "r") == []


def test_get_submodules_api_non_file_type():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(return_value={"type": "symlink"})
    assert c.get_submodules("o", "r") == []


def test_get_submodules_api_404_returns_empty():
    c = GitHubAPIClient("t")
    resp = MagicMock(status_code=404)
    err = requests.exceptions.HTTPError(response=resp)
    c.rest_request = MagicMock(side_effect=err)
    assert c.get_submodules("o", "r") == []


def test_get_submodules_api_other_http_error_raises():
    c = GitHubAPIClient("t")
    resp = MagicMock(status_code=500)
    err = requests.exceptions.HTTPError(response=resp)
    c.rest_request = MagicMock(side_effect=err)
    with pytest.raises(requests.exceptions.HTTPError):
        c.get_submodules("o", "r")


def test_get_submodules_generic_exception_returns_empty():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(side_effect=RuntimeError("boom"))
    assert c.get_submodules("o", "r") == []


def test_get_tag_sha_none_when_empty_response():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(return_value={})
    assert c.get_tag_sha("o", "r", "v1") is None


def test_get_tag_sha_returns_object_sha():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(
        return_value={"object": {"sha": "abc", "type": "commit"}}
    )
    assert c.get_tag_sha("o", "r", "v1") == "abc"


def test_get_tag_published_at_none_when_no_author():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(return_value={"commit": {}})
    assert c.get_tag_published_at("o", "r", "sha1") is None


def test_get_tag_published_at_parses_date():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(
        return_value={
            "author": {"date": "2020-01-15T10:00:00Z"},
        }
    )
    dt = c.get_tag_published_at("o", "r", "sha1")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is None or dt.tzinfo == timezone.utc
