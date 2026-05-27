"""Shared collector abstractions (optional Pinecone hooks, command adapter)."""

from core.collectors.base_collector import (
    AbstractCollector,
    CollectorRunnable,
)
from core.collectors.command_base import BaseCollectorCommand
from core.errors import CollectorFailureCategory, classify_failure

__all__ = [
    "AbstractCollector",
    "BaseCollectorCommand",
    "CollectorFailureCategory",
    "CollectorRunnable",
    "classify_failure",
]
