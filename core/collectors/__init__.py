"""Shared collector abstractions (optional Pinecone hooks, command adapter)."""

from core.collectors.base_collector import (
    AbstractCollector,
    CollectorRunnable,
)
from core.collectors.command_base import BaseCollectorCommand
from core.errors import CollectorFailureCategory, classify_failure
from core.activity_record import GenericActivityRecord
from core.incremental_state import GenericIncrementalState
from core.tracker_result import GenericTrackerResult

__all__ = [
    "AbstractCollector",
    "BaseCollectorCommand",
    "CollectorFailureCategory",
    "CollectorRunnable",
    "GenericActivityRecord",
    "GenericIncrementalState",
    "GenericTrackerResult",
    "classify_failure",
]
