"""Tests for git_ops.list_remote_directory."""

from unittest.mock import MagicMock, patch

import pytest

from core.operations.github_ops import git_ops


@patch(
    "core.operations.github_ops.git_ops._list_remote_directory_graphql",
    return_value=["issues/2024/x.md"],
)
def test_list_remote_directory_returns_paths(_mock_gql):
    out = git_ops.list_remote_directory(
        "boostorg", "boost", "master", "issues/2024", token="tok"
    )
    assert out == ["issues/2024/x.md"]


@patch(
    "core.operations.github_ops.git_ops._list_remote_directory_graphql",
    side_effect=RuntimeError("graphql failed"),
)
@patch("core.operations.github_ops.git_ops.get_github_token", return_value="tok")
def test_list_remote_directory_swallows_exceptions(_mock_token, _mock_gql):
    assert git_ops.list_remote_directory("o", "r", "main", "src") == []


@patch("core.operations.github_ops.git_ops.requests.Session")
def test_list_remote_directory_graphql_builds_paths(mock_session_cls):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "repository": {
                "object": {
                    "entries": [
                        {"name": "f.md", "type": "blob"},
                        {"name": "sub", "type": "tree"},
                    ],
                },
            },
        },
    }
    mock_resp.raise_for_status = MagicMock()
    mock_sess = MagicMock()
    mock_sess.post.return_value = mock_resp
    mock_session_cls.return_value = mock_sess

    out = git_ops._list_remote_directory_graphql("o", "r", "main", "issues/2024", "tok")
    assert out == ["issues/2024/f.md"]


@patch("core.operations.github_ops.git_ops.requests.Session")
def test_list_remote_directory_graphql_root_prefix(mock_session_cls):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "repository": {"object": {"entries": [{"name": "README", "type": "blob"}]}}
        },
    }
    mock_resp.raise_for_status = MagicMock()
    mock_sess = MagicMock()
    mock_sess.post.return_value = mock_resp
    mock_session_cls.return_value = mock_sess
    out = git_ops._list_remote_directory_graphql("o", "r", "main", "", "tok")
    assert out == ["README"]


@patch("core.operations.github_ops.git_ops.requests.Session")
def test_list_remote_directory_graphql_errors_raise(mock_session_cls):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"errors": [{"message": "bad query"}]}
    mock_resp.raise_for_status = MagicMock()
    mock_sess = MagicMock()
    mock_sess.post.return_value = mock_resp
    mock_session_cls.return_value = mock_sess
    with pytest.raises(RuntimeError, match="bad query"):
        git_ops._list_remote_directory_graphql("o", "r", "main", "p", "tok")


@patch("core.operations.github_ops.git_ops.requests.Session")
def test_list_remote_directory_graphql_missing_object(mock_session_cls):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"repository": {"object": None}}}
    mock_resp.raise_for_status = MagicMock()
    mock_sess = MagicMock()
    mock_sess.post.return_value = mock_resp
    mock_session_cls.return_value = mock_sess
    assert git_ops._list_remote_directory_graphql("o", "r", "main", "p", "tok") == []
