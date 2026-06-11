"""Frozen DTOs implementing :mod:`core.protocols` for Clang GitHub tracker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.protocol_dto import IncrementalStateDataclass, TrackerResultDataclass


@dataclass(frozen=True, repr=False)
class ClangGithubTrackerResult(TrackerResultDataclass):
    """Structured :class:`~core.protocols.TrackerResult` for Clang sync outcomes."""

    @classmethod
    def from_sync(
        cls,
        *,
        commits_saved: int,
        issue_count: int,
        pr_count: int,
        md_files: int = 0,
    ) -> ClangGithubTrackerResult:
        return cls(
            success=True,
            counts={
                "commits": commits_saved,
                "issues": issue_count,
                "pull_requests": pr_count,
                "md_files": md_files,
            },
        )

    @classmethod
    def dry_run(cls) -> ClangGithubTrackerResult:
        return cls(success=True, counts={})


@dataclass(frozen=True, repr=False)
class ClangGithubIncrementalState(IncrementalStateDataclass):
    """Checkpoint between Clang GitHub runs."""

    @classmethod
    def from_watermarks(
        cls,
        *,
        start_commit: datetime | str | None,
        start_item: datetime | str | None,
    ) -> ClangGithubIncrementalState:
        def _marker_value(value: datetime | str | None) -> str | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        commit_marker = _marker_value(start_commit)
        item_marker = _marker_value(start_item)
        marker_parts = [p for p in (commit_marker, item_marker) if p is not None]
        marker = "|".join(marker_parts) if marker_parts else None
        return cls(
            checkpoint_token="clang:llvm/llvm-project",
            human_readable_marker=marker,
            extras={"start_commit": commit_marker, "start_item": item_marker},
        )
