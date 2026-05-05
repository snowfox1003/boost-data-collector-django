"""Django management command base class for CollectorBase-backed collectors."""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core.collectors.base import CollectorBase

logger = logging.getLogger(__name__)


class BaseCollectorCommand(BaseCommand):
    """Runs ``get_collector(**options).run()`` then ``sync_pinecone()`` with shared error handling."""

    @abstractmethod
    def get_collector(self, **options: Any) -> CollectorBase:
        """Instantiate the collector from parsed CLI options."""

    def handle(self, *args: Any, **options: Any) -> None:
        collector = self.get_collector(**options)
        self._run_collector_phase(collector, collector.run)
        self._run_collector_phase(collector, collector.sync_pinecone)

    def _run_collector_phase(
        self,
        collector: CollectorBase,
        phase: Any,
    ) -> None:
        """
        Run one collector phase (``run`` or ``sync_pinecone``).

        On unexpected exceptions, :meth:`CollectorBase.handle_error` is invoked with
        ``collector._error_phase`` set to the phase name for structured logs
        (``collector``, ``collector_phase``, ``failure_category`` on the log record).
        """
        phase_name = getattr(phase, "__name__", str(phase))
        setattr(collector, "_error_phase", phase_name)
        try:
            phase()
        except CommandError:
            logger.error(
                "Collector raised CommandError during %s",
                phase_name,
                extra={
                    "collector": collector.__class__.__name__,
                    "collector_phase": phase_name,
                    "failure_category": "command",
                },
            )
            raise
        except Exception as exc:
            collector.handle_error(exc)
            raise
        finally:
            if hasattr(collector, "_error_phase"):
                delattr(collector, "_error_phase")
