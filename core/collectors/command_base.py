"""Django management command base class for CollectorRunnable-backed collectors."""

# Design notes (review summary):
# - Template method: handle() -> get_collector(**options) -> phase(run) -> phase(sync_pinecone).
# - ABC: subclasses that omit get_collector() raise TypeError at instantiation, not at import.
# - Each _run_collector_phase uses try/except/finally; finally clears _error_phase even if
#   handle_error, classify_failure, or logging raises (double fault cleanup).
# - classify_failure (core.errors) maps a core dependency surface; many SDK/DB errors stay
#   unknown—override handle_error on the collector when you need a specific category.

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core.collectors.base_collector import CollectorRunnable

logger = logging.getLogger(__name__)


class BaseCollectorCommand(ABC, BaseCommand):
    """
    Thin Django ``BaseCommand`` adapter using the template-method pattern.

    **Flow:** :meth:`django.core.management.base.BaseCommand.handle` is implemented as
    ``get_collector(**options)``, then :meth:`_run_collector_phase` with ``collector.run``,
    then :meth:`_run_collector_phase` with ``collector.sync_pinecone``.

    **``get_collector`` contract:** Must return a :class:`CollectorRunnable`—any object
    with ``run()``, ``sync_pinecone()``, and ``handle_error(exc)``. Typical implementations
    return an :class:`~core.collectors.base_collector.AbstractCollector` instance (or
    any other :class:`CollectorRunnable`). Subclasses that
    do not implement :meth:`get_collector` cannot be instantiated (``TypeError`` from
    ``abc``), which surfaces as soon as the command object is constructed, usually when
    Django loads the command.

    **Errors:** :class:`~django.core.management.base.CommandError` is logged with
    ``failure_category`` set to ``\"command\"`` and re-raised without calling
    ``handle_error``. Any other :class:`Exception` is passed to ``collector.handle_error``
    (which classifies via :func:`core.errors.classify_failure` and logs), then re-raised.
    A ``finally`` block always removes ``collector._error_phase`` after each phase.
    """

    @abstractmethod
    def get_collector(self, **options: Any) -> CollectorRunnable:
        """
        Build the collector instance from parsed CLI options.

        Args:
            **options: Keyword arguments forwarded from :meth:`handle` (Django-parsed
                command-line options and defaults).

        Returns:
            A :class:`CollectorRunnable` executed by :meth:`handle` (``run`` then
            ``sync_pinecone``).
        """

    def handle(self, *args: Any, **options: Any) -> None:
        collector = self.get_collector(**options)
        self._run_collector_phase(collector, collector.run)
        self._run_collector_phase(collector, collector.sync_pinecone)

    def _run_collector_phase(
        self,
        collector: CollectorRunnable,
        phase: Any,
    ) -> None:
        """
        Run a single zero-argument callable phase on *collector*.

        Sets ``collector._error_phase`` to the callable's ``__name__`` (for example
        ``\"run\"`` or ``\"sync_pinecone\"``) before invoking *phase*, clears it in
        ``finally``, and routes failures per :class:`BaseCollectorCommand` error rules.

        Args:
            collector: Object providing ``handle_error`` for non-command failures.
            phase: Bound method or callable with no arguments (typically
                ``collector.run`` or ``collector.sync_pinecone``).

        Returns:
            None
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
