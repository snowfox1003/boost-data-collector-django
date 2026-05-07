"""Tests for GitHubAPIClient GraphQL and .gitmodules helpers."""

from unittest.mock import MagicMock, patch

import pytest

from core.operations.github_ops.client import GitHubAPIClient


def test_graphql_request_returns_data():
    client = GitHubAPIClient("t")
    ok = MagicMock()
    ok.status_code = 200
    ok.json = MagicMock(return_value={"data": {"repository": {"id": "1"}}})
    ok.raise_for_status = MagicMock()
    client._do_request = MagicMock(return_value=ok)
    client._raise_if_error_and_update_rate_limit = MagicMock()
    out = client.graphql_request("query Q { __typename }")
    assert out["data"]["repository"]["id"] == "1"


def test_graphql_request_raises_on_errors_key():
    client = GitHubAPIClient("t")
    ok = MagicMock()
    ok.status_code = 200
    ok.json = MagicMock(
        return_value={"errors": [{"message": "bad"}, {"message": "worse"}]}
    )
    ok.raise_for_status = MagicMock()
    client._do_request = MagicMock(return_value=ok)
    client._raise_if_error_and_update_rate_limit = MagicMock()
    with pytest.raises(Exception, match="GraphQL errors"):
        client.graphql_request("query { x }")


def test_get_submodules_from_file_missing_returns_empty():
    client = GitHubAPIClient("t")
    assert client.get_submodules_from_file("/nonexistent/.gitmodules") == []


def test_get_submodules_from_file_read_error_returns_empty(tmp_path):
    client = GitHubAPIClient("t")
    p = tmp_path / "gm"
    p.write_text('[submodule "a"]\n', encoding="utf-8")
    real_open = open

    def selective_open(name, *args, **kwargs):
        if str(name) == str(p):
            raise OSError("disk")
        return real_open(name, *args, **kwargs)

    with patch("builtins.open", selective_open):
        assert client.get_submodules_from_file(str(p)) == []


def test_parse_gitmodules_via_local_file(tmp_path):
    client = GitHubAPIClient("t")
    content = """
[submodule "libs/foo"]
path = libs/foo
url = ../foo.git
"""
    p = tmp_path / ".gitmodules"
    p.write_text(content, encoding="utf-8")
    out = client.get_submodules_from_file(str(p), default_owner="boostorg")
    assert len(out) == 1
    assert "foo" in out[0].get("repo_name", "")
