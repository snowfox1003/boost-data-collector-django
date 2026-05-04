"""
Abstract collector contract for data-collection apps.

Concrete collectors may wrap other Django commands (see DjangoCommandCollector)
or implement custom ``run()`` logic. Schedules invoke per-app management
commands (``run_scheduled_collectors`` / YAML); subclasses may override
``handle_error`` and ``sync_pinecone`` for shared behavior.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from django.core.management import call_command

from core.errors import classify_failure

logger = logging.getLogger(__name__)


class CollectorBase(ABC):
    """Base type for collectors run via management commands or YAML schedules."""

    @abstractmethod
    def run(self) -> None:
        """Execute the collector work unit."""

    def handle_error(self, exc: BaseException) -> None:
        """Log or surface failures; override for structured error contracts."""
        category = classify_failure(exc)
        phase = getattr(self, "_error_phase", None) or "unknown"
        collector_id = self.__class__.__name__
        logger.exception(
            "Collector failed: collector=%s phase=%s failure_category=%s",
            collector_id,
            phase,
            category.value,
            extra={
                "collector": collector_id,
                "collector_phase": phase,
                "failure_category": category.value,
            },
        )

    def sync_pinecone(self) -> None:
        """Optional post-run Pinecone sync; default is no-op."""
        return None


class DjangoCommandCollector(CollectorBase):
    """Runs a registered Django management command by name."""

    __slots__ = ("command_name",)

    def __init__(self, command_name: str) -> None:
        self.command_name = command_name

    def run(self) -> None:
        call_command(self.command_name)
