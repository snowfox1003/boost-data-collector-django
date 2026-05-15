"""Tests for :mod:`github_activity_tracker.protocol_impl`."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.protocols import TrackerResult

from github_activity_tracker.protocol_impl import (
    GitHubSyncTrackerResult,
    sync_github_tracker_result,
)


def test_sync_github_tracker_result_wraps_sync_github_dict():
    repo = MagicMock()
    with patch("github_activity_tracker.protocol_impl.sync_github") as m:
        m.return_value = {"issues": [1, 2], "pull_requests": [9]}
        out = sync_github_tracker_result(
            repo, start_date=datetime(2024, 1, 1, tzinfo=timezone.utc)
        )
    m.assert_called_once()
    assert isinstance(out, TrackerResult)
    assert out.counts == {"issues": 2, "pull_requests": 1}
    assert out.success is True


def test_github_sync_tracker_result_from_sync_dict():
    r = GitHubSyncTrackerResult.from_sync_dict({"issues": [], "pull_requests": [1]})
    assert r.counts["issues"] == 0
    assert r.counts["pull_requests"] == 1
