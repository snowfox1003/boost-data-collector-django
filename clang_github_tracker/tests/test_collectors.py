"""Tests for clang_github_tracker.collectors."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management.base import CommandError

from clang_github_tracker.collectors import (
    ClangGithubTrackerCollector,
    _run_pinecone_sync,
)


def test_run_pinecone_sync_skips_when_app_type_empty(caplog):
    caplog.set_level(logging.WARNING)
    _run_pinecone_sync("", "ns", "some.module.fn")
    assert "CLANG_GITHUB_PINECONE_APP_TYPE is empty" in caplog.text


def test_run_pinecone_sync_skips_when_namespace_empty(caplog):
    caplog.set_level(logging.WARNING)
    _run_pinecone_sync("app", "", "some.module.fn")
    assert "CLANG_GITHUB_PINECONE_NAMESPACE is empty" in caplog.text


@patch("clang_github_tracker.collectors.call_command")
def test_run_pinecone_sync_calls_sync_command(mock_call_command, caplog):
    caplog.set_level(logging.INFO)
    _run_pinecone_sync("myapp", "myspace", "pkg.preprocess")
    mock_call_command.assert_called_once_with(
        "run_cppa_pinecone_sync",
        app_type="myapp",
        namespace="myspace",
        preprocessor="pkg.preprocess",
    )
    assert "pinecone sync completed" in caplog.text


@patch(
    "clang_github_tracker.collectors.call_command",
    side_effect=RuntimeError("cmd failed"),
)
def test_run_pinecone_sync_logs_when_call_command_fails(_mock_call, caplog):
    caplog.set_level(logging.WARNING)
    _run_pinecone_sync("a", "b", "c")
    assert "skipped/failed" in caplog.text


def _collector(**overrides):
    kwargs = dict(
        dry_run=False,
        skip_github_sync=False,
        skip_markdown_export=True,
        skip_remote_push=True,
        skip_pinecone=True,
        since="2024-01-01T00:00:00Z",
        until="2024-01-02T00:00:00Z",
    )
    kwargs.update(overrides)
    return ClangGithubTrackerCollector(**kwargs)


@patch("clang_github_tracker.collectors.sync_clang_github_activity")
@patch("clang_github_tracker.collectors.clang_state.resolve_start_end_dates")
def test_collector_sync_failure_raises(_resolve, mock_sync):
    """Uncaught errors propagate; structured logging is done in CollectorBase.handle_error when the management command wraps run()."""
    _resolve.return_value = ("sc", "si", None)
    mock_sync.side_effect = RuntimeError("sync boom")
    c = _collector(skip_github_sync=False)
    with pytest.raises(RuntimeError, match="sync boom"):
        c.run()


@patch("clang_github_tracker.collectors.clang_state.resolve_start_end_dates")
def test_collector_invalid_since_raises_command_error(_resolve):
    c = _collector(since="not-a-date", until="2024-01-02T00:00:00Z")
    with pytest.raises(CommandError):
        c.run()
    _resolve.assert_not_called()


@patch("clang_github_tracker.collectors.clang_state.resolve_start_end_dates")
def test_collector_dry_run_logs_skip_github_when_skipped(_resolve, caplog):
    caplog.set_level(logging.INFO)
    _resolve.return_value = ("sc", "si", None)
    c = _collector(dry_run=True, skip_github_sync=True)
    c.run()
    assert "dry-run: skipping GitHub sync" in caplog.text


@patch("clang_github_tracker.collectors.write_md_files")
@patch("clang_github_tracker.collectors.sync_clang_github_activity")
@patch("clang_github_tracker.collectors.clang_state.resolve_start_end_dates")
def test_collector_skip_markdown_export_logs(_resolve, mock_sync, _mock_write, caplog):
    caplog.set_level(logging.INFO)
    _resolve.return_value = ("sc", "si", None)
    mock_sync.return_value = (0, [1], [2])

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with patch(
            "clang_github_tracker.collectors.get_workspace_root", return_value=root
        ):
            c = _collector(
                skip_github_sync=False,
                skip_markdown_export=True,
            )
            c.run()
    assert "skipping Markdown export (--skip-markdown-export)" in caplog.text


@patch("clang_github_tracker.collectors.write_md_files")
@patch("clang_github_tracker.collectors.sync_clang_github_activity")
@patch("clang_github_tracker.collectors.clang_state.resolve_start_end_dates")
def test_collector_no_issues_after_sync_skips_md_export(
    _resolve, mock_sync, mock_write, caplog
):
    caplog.set_level(logging.INFO)
    _resolve.return_value = ("sc", "si", None)
    mock_sync.return_value = (0, [], [])

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with patch(
            "clang_github_tracker.collectors.get_workspace_root", return_value=root
        ):
            c = _collector(
                skip_github_sync=False,
                skip_markdown_export=False,
            )
            c.run()
    mock_write.assert_not_called()
    assert "no issues/PRs synced; skipping MD export" in caplog.text


@patch("clang_github_tracker.collectors.write_md_files")
@patch("clang_github_tracker.collectors.sync_clang_github_activity")
@patch("clang_github_tracker.collectors.clang_state.resolve_start_end_dates")
def test_collector_skip_sync_skips_md_when_export_enabled(
    _resolve, mock_sync, mock_write, caplog
):
    caplog.set_level(logging.INFO)
    _resolve.return_value = ("sc", "si", None)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with patch(
            "clang_github_tracker.collectors.get_workspace_root", return_value=root
        ):
            c = _collector(
                skip_github_sync=True,
                skip_markdown_export=False,
            )
            c.run()
    mock_sync.assert_not_called()
    mock_write.assert_not_called()
    assert "skipped Markdown export (no sync in this run)" in caplog.text
