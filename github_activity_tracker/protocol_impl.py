"""Frozen DTOs implementing :mod:`core.protocols` for GitHub activity sync."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from github_activity_tracker.sync import sync_github


@dataclass(frozen=True)
class GitHubSyncTrackerResult:
    """Structured :class:`~core.protocols.TrackerResult` for ``sync_github`` outcomes."""

    success: bool
    counts: Mapping[str, int]

    @classmethod
    def from_sync_dict(cls, d: dict[str, list[int]]) -> GitHubSyncTrackerResult:
        issues = d.get("issues") or []
        prs = d.get("pull_requests") or []
        return cls(
            success=True,
            counts={"issues": len(issues), "pull_requests": len(prs)},
        )


def sync_github_tracker_result(
    repo: Any,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> GitHubSyncTrackerResult:
    """Run :func:`~github_activity_tracker.sync.sync_github.sync_github` and return a protocol-friendly DTO."""
    raw = sync_github(repo, start_date=start_date, end_date=end_date)
    return GitHubSyncTrackerResult.from_sync_dict(raw)


@dataclass(frozen=True)
class GitHubActivityRecord:
    """Single issue/PR touch for cross-layer logging or bridges."""

    source_system: str
    external_id: str
    occurred_at: str
    activity_type: str
    actor_external_id: str
    source_url: str | None
    summary: str

    @classmethod
    def from_issue(
        cls,
        *,
        repo_id: int,
        issue_number: int,
        occurred_at: str = "",
        summary: str = "",
    ) -> GitHubActivityRecord:
        return cls(
            source_system="github",
            external_id=f"{repo_id}:issue:{issue_number}",
            occurred_at=occurred_at,
            activity_type="github.issue",
            actor_external_id="",
            source_url=None,
            summary=summary[:2000],
        )


@dataclass(frozen=True)
class GitHubIncrementalState:
    """Opaque + human-readable sync watermark (app-specific *extras*)."""

    checkpoint_token: str | None
    human_readable_marker: str | None
    extras: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_repo_watermark(
        cls, *, repo_id: int, marker: str
    ) -> GitHubIncrementalState:
        return cls(
            checkpoint_token=f"github:repo:{repo_id}",
            human_readable_marker=marker,
            extras={"repo_id": repo_id},
        )
