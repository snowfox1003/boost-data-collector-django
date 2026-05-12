"""
Abstract collector contract for data-collection apps.

Concrete collectors may wrap other Django commands (see DjangoCommandCollector)
or implement custom ``run()`` logic. Schedules invoke per-app management
commands (``run_scheduled_collectors`` / YAML); subclasses may override
``handle_error`` and ``sync_pinecone`` for shared behavior.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from django.core.management import call_command

from core.collectors.base_collector import _CollectorLifecycleMixin


class CollectorBase(_CollectorLifecycleMixin, ABC):
    """Base type for collectors run via management commands or YAML schedules."""

    @abstractmethod
    def run(self) -> None:
        """Execute the collector work unit."""


class DjangoCommandCollector(CollectorBase):
    """Runs a registered Django management command by name."""

    __slots__ = ("command_name",)

    def __init__(self, command_name: str) -> None:
        self.command_name = command_name

    def run(self) -> None:
        call_command(self.command_name)
