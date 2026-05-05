"""Shared collector abstractions (optional Pinecone hooks, command adapter)."""

from core.collectors.base import CollectorBase, DjangoCommandCollector
from core.collectors.command_base import BaseCollectorCommand
from core.errors import CollectorFailureCategory, classify_failure

__all__ = [
    "BaseCollectorCommand",
    "CollectorBase",
    "CollectorFailureCategory",
    "DjangoCommandCollector",
    "classify_failure",
]
