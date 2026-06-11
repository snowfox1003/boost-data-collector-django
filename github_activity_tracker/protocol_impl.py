"""Frozen DTOs implementing :mod:`core.protocols` for GitHub activity sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from core.activity_types import (
    ActivityType,
    LegacyActivityRecordDict,
    SourceSystem,
    activity_record_to_legacy_dict,
    migrate_legacy_activity_fields,
)
from core.protocol_dto import (
    ActivityRecordDataclass,
    IncrementalStateDataclass,
    TrackerResultDataclass,
)
from github_activity_tracker.sync import sync_github


@dataclass(frozen=True, repr=False)
class GitHubSyncTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for ``sync_github`` outcomes."""

    @classmethod
    def from_sync_dict(cls, d: dict[str, list[int]]) -> GitHubSyncTrackerResult:
        issues = d.get("issues") or []
        prs = d.get("pull_requests") or []
        return cls(
            success=True,
            counts={"issues": len(issues), "pull_requests": len(prs)},
        )

    @classmethod
    def merge(cls, *results: GitHubSyncTrackerResult) -> GitHubSyncTrackerResult:
        """Combine per-repo results into one aggregate."""
        if not results:
            return cls(success=True, counts={})
        counts: dict[str, int] = {}
        errors: list[str] = []
        success = True
        for r in results:
            if not r.success:
                success = False
            for k, v in r.counts.items():
                counts[k] = counts.get(k, 0) + v
            errors.extend(r.errors)
        return cls(success=success, counts=counts, errors=tuple(errors))


def sync_github_tracker_result(
    repo: Any,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> GitHubSyncTrackerResult:
    """Run :func:`~github_activity_tracker.sync.sync_github.sync_github` and return a protocol-friendly DTO."""
    raw = sync_github(repo, start_date=start_date, end_date=end_date)
    return GitHubSyncTrackerResult.from_sync_dict(raw)


@dataclass(frozen=True, repr=False)
class GitHubActivityRecord(ActivityRecordDataclass):
    """Single issue/PR touch for cross-layer logging or bridges."""

    def to_legacy_dict(self) -> LegacyActivityRecordDict:
        """Tier-C workspace bridge format; prefer :meth:`asdict` for canonical protocol JSON."""
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


@dataclass(frozen=True, repr=False)
class GitHubIncrementalState(IncrementalStateDataclass):
    """Opaque + human-readable sync watermark (app-specific *extras*)."""

    @classmethod
    def from_repo_watermark(
        cls, *, repo_id: int, marker: str
    ) -> GitHubIncrementalState:
        return cls(
            checkpoint_token=f"github:repo:{repo_id}",
            human_readable_marker=marker,
            extras={"repo_id": repo_id},
        )
