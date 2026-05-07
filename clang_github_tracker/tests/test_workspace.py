"""Tests for clang_github_tracker.workspace."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clang_github_tracker import workspace as ws


def test_sanitize_segment_via_get_raw_repo_dir_invalid():
    with pytest.raises(ValueError, match="Invalid GitHub owner"):
        ws.get_raw_repo_dir(owner="", repo="llvm-project", create=False)
    with pytest.raises(ValueError, match="Invalid GitHub owner"):
        ws.get_raw_repo_dir(owner="bad owner", repo="y", create=False)
    with pytest.raises(ValueError, match="Invalid GitHub repo"):
        ws.get_raw_repo_dir(owner="llvm", repo="bad/repo", create=False)


@patch("clang_github_tracker.workspace.get_workspace_path")
def test_get_raw_root_creates_parents(mock_get_ws: MagicMock, tmp_path: Path):
    _app_dir = tmp_path / "gh"
    mock_get_ws.return_value = tmp_path / "raw"
    root = ws.get_raw_root()
    assert root == tmp_path / "raw" / "github_activity_tracker"
    assert root.is_dir()


@patch("clang_github_tracker.workspace.get_workspace_path")
def test_get_raw_repo_dir_create_false_no_mkdir(mock_get_ws: MagicMock, tmp_path: Path):
    mock_get_ws.return_value = tmp_path / "raw"
    p = ws.get_raw_repo_dir("llvm", "llvm-project", create=False)
    assert p == tmp_path / "raw" / "github_activity_tracker" / "llvm" / "llvm-project"
    assert not p.exists()


@patch("clang_github_tracker.workspace.get_workspace_path")
def test_get_raw_repo_dir_default_create_makes_dirs(
    mock_get_ws: MagicMock, tmp_path: Path
):
    mock_get_ws.return_value = tmp_path / "raw"
    p = ws.get_raw_repo_dir("llvm", "llvm-project")
    assert p.is_dir()
    assert p == tmp_path / "raw" / "github_activity_tracker" / "llvm" / "llvm-project"
