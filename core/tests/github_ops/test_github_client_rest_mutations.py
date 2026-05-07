"""Tests for GitHubAPIClient REST PUT/DELETE, file SHA, and paginated GET URL."""

from unittest.mock import MagicMock

import pytest
import requests

from core.operations.github_ops.client import GitHubAPIClient


def _ok_json(data, status=200, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json = MagicMock(return_value=data)
    r.raise_for_status = MagicMock()
    r.content = b"raw-bytes"
    return r


def test_rest_put_returns_json():
    c = GitHubAPIClient("t")
    r = _ok_json({"sha": "abc"})
    c._do_request = MagicMock(return_value=r)
    c._raise_if_error_and_update_rate_limit = MagicMock()
    out = c.rest_put("/repos/o/r/contents/p", json_data={"message": "m"})
    assert out["sha"] == "abc"


def test_rest_delete_returns_none_on_204():
    c = GitHubAPIClient("t")
    r = MagicMock()
    r.status_code = 204
    r.headers = {}
    r.json = MagicMock()
    r.raise_for_status = MagicMock()
    c._do_request = MagicMock(return_value=r)
    c._raise_if_error_and_update_rate_limit = MagicMock()
    assert c.rest_delete("/repos/o/r/contents/p", json_data={"message": "x"}) is None


def test_rest_delete_returns_json_when_not_204():
    c = GitHubAPIClient("t")
    r = _ok_json({"id": 1}, status=200)
    c._do_request = MagicMock(return_value=r)
    c._raise_if_error_and_update_rate_limit = MagicMock()
    assert c.rest_delete("/repos/o/r/git/refs/tags/t", json_data={})["id"] == 1


def test_get_file_sha_returns_sha():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(return_value={"sha": "deadbeef", "type": "file"})
    assert c.get_file_sha("o", "r", "README.md") == "deadbeef"


def test_get_file_sha_returns_none_for_directory_listing():
    c = GitHubAPIClient("t")
    c.rest_request = MagicMock(return_value=[{"name": "a"}])
    assert c.get_file_sha("o", "r", "dir") is None


def test_get_file_sha_returns_none_on_404():
    c = GitHubAPIClient("t")
    resp = MagicMock()
    resp.status_code = 404
    err = requests.exceptions.HTTPError(response=resp)
    c.rest_request = MagicMock(side_effect=err)
    assert c.get_file_sha("o", "r", "missing") is None


def test_get_file_sha_re_raises_non_404():
    c = GitHubAPIClient("t")
    resp = MagicMock()
    resp.status_code = 500
    err = requests.exceptions.HTTPError(response=resp)
    c.rest_request = MagicMock(side_effect=err)
    with pytest.raises(requests.exceptions.HTTPError):
        c.get_file_sha("o", "r", "x")


def test_create_or_update_file_calls_rest_put():
    c = GitHubAPIClient("t")
    c.rest_put = MagicMock(return_value={"commit": {}})
    c.create_or_update_file(
        "o", "r", "f.txt", "Y29udGVudA==", "msg", branch="main", sha="old"
    )
    kw = c.rest_put.call_args[1]["json_data"]
    assert kw["sha"] == "old"


def test_delete_file_returns_none_when_no_sha():
    c = GitHubAPIClient("t")
    c.get_file_sha = MagicMock(return_value=None)
    assert c.delete_file("o", "r", "gone.txt", "del") is None


def test_delete_file_calls_rest_delete_when_sha_present():
    c = GitHubAPIClient("t")
    c.get_file_sha = MagicMock(return_value="sha1")
    c.rest_delete = MagicMock(return_value={"commit": {}})
    c.delete_file("o", "r", "f.txt", "m", branch="dev")
    c.get_file_sha.assert_called_once_with("o", "r", "f.txt", ref="dev")
    c.rest_delete.assert_called_once_with(
        "/repos/o/r/contents/f.txt",
        json_data={"message": "m", "sha": "sha1", "branch": "dev"},
    )


def test_rest_request_url_with_all_links_hits_do_request():
    c = GitHubAPIClient("t")
    r = _ok_json(
        {"items": []},
        headers={"Link": '<https://api.github.com/repos/o/r?page=2>; rel="next"'},
    )
    c._rest_get_url = MagicMock(return_value=r)
    start = "https://api.github.com/repos/o/r/issues?page=1"
    data, links = c.rest_request_url_with_all_links(start)
    assert data == {"items": []}
    assert links["next"] == "https://api.github.com/repos/o/r?page=2"
    # Single GET only; callers follow ``links["next"]`` themselves (no auto-traverse).
    c._rest_get_url.assert_called_once_with(start)


def test_rest_request_url_returns_data_and_next():
    c = GitHubAPIClient("t")
    r = _ok_json(
        [1, 2],
        headers={"Link": '<https://api.github.com/next>; rel="next"'},
    )
    c._rest_get_url = MagicMock(return_value=r)
    data, nxt = c.rest_request_url("https://api.github.com/repos/o/r/issues?per_page=1")
    assert data == [1, 2]
    assert nxt == "https://api.github.com/next"


def test_rest_get_raises_http_error_from_raise_for_status():
    c = GitHubAPIClient("t")
    bad = MagicMock()
    bad.status_code = 500
    bad.headers = {}
    bad.raise_for_status = MagicMock(
        side_effect=requests.exceptions.HTTPError(response=bad)
    )
    c._do_request = MagicMock(return_value=bad)
    with pytest.raises(requests.exceptions.HTTPError):
        c._rest_get("/repos/o/r/issues")
