"""Frozen DTOs implementing :mod:`core.protocols` for GitHub activity sync."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from core.activity_types import (
    ActivityType,
    ActorExternalId,
    LegacyActivityRecordDict,
    SourceSystem,
    activity_record_to_legacy_dict,
    ensure_activity_occurred_at,
    migrate_legacy_activity_fields,
)
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

    source_system: SourceSystem
    external_id: str
    occurred_at: datetime | None
    activity_type: ActivityType
    actor_external_id: ActorExternalId
    source_url: str | None
    summary: str

    def __post_init__(self) -> None:
        if self.occurred_at is not None:
            object.__setattr__(
                self, "occurred_at", ensure_activity_occurred_at(self.occurred_at)
            )

    def to_legacy_dict(self) -> LegacyActivityRecordDict:
        return activity_record_to_legacy_dict(
            source_system=self.source_system,
            external_id=self.external_id,
            occurred_at=self.occurred_at,
            activity_type=self.activity_type,
            actor_id=self.actor_external_id,
            source_url=self.source_url,
            summary=self.summary,
        )

    @classmethod
    def from_issue(
        cls,
        *,
        repo_id: int,
        issue_number: int,
        occurred_at: str | datetime | None = "",
        summary: str = "",
    ) -> GitHubActivityRecord:
        source, occurred, atype, actor = migrate_legacy_activity_fields(
            source_system=SourceSystem.GITHUB.value,
            occurred_at=occurred_at,
            activity_type=ActivityType.github_issue(),
            actor_external_id_raw="",
        )
        return cls(
            source_system=source,
            external_id=f"{repo_id}:issue:{issue_number}",
            occurred_at=occurred,
            activity_type=atype,
            actor_external_id=actor,
            source_url=None,
            summary=summary[:2000],
        )

    @classmethod
    def from_legacy_dict(
        cls,
        data: Mapping[str, Any],
        *,
        external_id: str,
        summary: str = "",
        source_url: str | None = None,
    ) -> GitHubActivityRecord:
        """Construct from string-keyed export/bridge payloads."""
        source, occurred, atype, actor = migrate_legacy_activity_fields(
            source_system=str(data.get("source_system") or SourceSystem.GITHUB.value),
            occurred_at=data.get("occurred_at") or data.get("created_at") or "",
            activity_type=str(data.get("activity_type") or ActivityType.github_issue()),
            actor_external_id_raw=data.get("actor_external_id")
            or data.get("actor_id")
            or "",
        )
        return cls(
            source_system=source,
            external_id=external_id,
            occurred_at=occurred,
            activity_type=atype,
            actor_external_id=actor,
            source_url=source_url,
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
