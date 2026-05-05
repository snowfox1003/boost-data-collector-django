"""Tests for slack_event_handler.workspace."""

from pathlib import Path
from unittest.mock import patch

import pytest

from slack_event_handler.workspace import (
    get_data_dir,
    get_workspace_root,
    set_working_directory,
)


@pytest.fixture
def mock_workspace_path(tmp_path):
    root = tmp_path / "slack_event_handler"
    root.mkdir(parents=True)
    return root


def test_get_workspace_root_uses_config_workspace():
    with patch("slack_event_handler.workspace.get_workspace_path") as m:
        m.return_value = Path("/tmp/slack_wh")
        assert get_workspace_root() == Path("/tmp/slack_wh")


def test_get_data_dir_creates_data_subdirectory(mock_workspace_path):
    with patch(
        "slack_event_handler.workspace.get_workspace_root",
        return_value=mock_workspace_path,
    ):
        d = get_data_dir()
        assert d == mock_workspace_path / "data"
        assert d.is_dir()


def test_set_working_directory_changes_cwd(mock_workspace_path):
    import os

    with patch(
        "slack_event_handler.workspace.get_workspace_root",
        return_value=mock_workspace_path,
    ):
        old = os.getcwd()
        try:
            set_working_directory()
            assert os.getcwd() == str(mock_workspace_path.resolve())
        finally:
            os.chdir(old)
