"""
Service layer for boost_collector_runner.

All creates/updates for this app's models must go through functions in this module.
See CONTRIBUTING.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.utils import timezone

from .models import CollectorGroupRunStatus


def record_group_success(
    group_id: str, *, when: Optional[datetime] = None
) -> CollectorGroupRunStatus:
    """Record a successful group batch run."""
    ts = when or timezone.now()
    obj, _created = CollectorGroupRunStatus.objects.update_or_create(
        group_id=group_id,
        defaults={
            "last_success_at": ts,
            "last_run_at": ts,
            "last_exit_code": 0,
        },
    )
    return obj


def record_group_failure(
    group_id: str,
    *,
    exit_code: int = 1,
    when: Optional[datetime] = None,
) -> CollectorGroupRunStatus:
    """Record a failed group batch run."""
    ts = when or timezone.now()
    obj, _created = CollectorGroupRunStatus.objects.update_or_create(
        group_id=group_id,
        defaults={
            "last_failure_at": ts,
            "last_run_at": ts,
            "last_exit_code": exit_code,
        },
    )
    return obj


def get_group_status(group_id: str) -> Optional[CollectorGroupRunStatus]:
    """Return status row for a group, or None if never run."""
    return CollectorGroupRunStatus.objects.filter(group_id=group_id).first()


def list_group_statuses() -> dict[str, CollectorGroupRunStatus]:
    """Return all group statuses keyed by group_id."""
    return {row.group_id: row for row in CollectorGroupRunStatus.objects.all()}
