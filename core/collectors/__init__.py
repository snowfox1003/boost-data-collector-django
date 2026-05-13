"""Shared collector abstractions (optional Pinecone hooks, command adapter)."""

from core.collectors.base import CollectorBase, DjangoCommandCollector
from core.collectors.base_collector import (
    AbstractCollector,
    CollectorRunnable,
)
from core.collectors.command_base import BaseCollectorCommand
from core.errors import CollectorFailureCategory, classify_failure

__all__ = [
    "AbstractCollector",
    "BaseCollectorCommand",
    "CollectorBase",
    "CollectorFailureCategory",
    "CollectorRunnable",
    "DjangoCommandCollector",
    "classify_failure",
]
