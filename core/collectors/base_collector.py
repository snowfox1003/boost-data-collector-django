"""
Structured collector contract: ``name``, ``validate_config``, ``collect``.

:class:`AbstractCollector` uses :class:`_CollectorLifecycleMixin` for
``handle_error`` / ``sync_pinecone`` so :class:`core.collectors.command_base.BaseCollectorCommand`
can invoke ``run`` then ``sync_pinecone`` unchanged.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from core.errors import classify_failure

logger = logging.getLogger(__name__)


@runtime_checkable
class CollectorRunnable(Protocol):
    """
    Structural type for objects executed by :class:`BaseCollectorCommand`.

    Implementations are typically :class:`AbstractCollector` subclasses (or any object
    satisfying this protocol). The command invokes :meth:`run`, then :meth:`sync_pinecone`, and
    routes failures through :meth:`handle_error` (except :class:`~django.core.management.base.CommandError`).
    """

    def run(self) -> None:
        """Main collection phase; see :class:`AbstractCollector`."""
        ...

    def sync_pinecone(self) -> None:
        """Optional post-run sync; may be a no-op."""
        ...

    def handle_error(self, exc: BaseException) -> None:
        """Log *exc* with structured ``failure_category``; must not swallow *exc*."""
        ...


class _CollectorLifecycleMixin:
    """
    Shared ``handle_error`` / ``sync_pinecone`` for collector implementations.

    Uses :func:`core.errors.classify_failure` (not a method on
    :class:`~core.errors.CollectorFailureCategory`) so log ``extra`` includes a stable
    ``failure_category`` enum value.

    **``_error_phase``:** Set only by :class:`~core.collectors.command_base.BaseCollectorCommand`
    around each phase; used when logging. If :func:`~core.errors.classify_failure`
    or logging raises, the command's ``finally`` still clears ``_error_phase`` on the
    collector instance.

    **Intentional gaps:** Many domain or SDK exceptions map to ``unknown``. Override
    :meth:`handle_error` when you need a different category or extra context.
    """

    def handle_error(self, exc: BaseException) -> None:
        """
        Log *exc* at exception level with structured fields for metrics and alerting.

        Args:
            exc: The exception from ``run`` or ``sync_pinecone`` (never a
                :class:`~django.core.management.base.CommandError`; those are handled
                in the command).

        ``logger.exception`` receives ``extra`` keys: ``collector``, ``collector_phase``,
        ``failure_category`` (string value of :class:`~core.errors.CollectorFailureCategory`).
        """
        category = classify_failure(exc)
        phase = getattr(self, "_error_phase", None) or "unknown"
        collector_id = getattr(self, "name", None)
        if not isinstance(collector_id, str) or not collector_id:
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
        """
        Optional post-run Pinecone sync; default is no-op.

        Returns:
            None
        """
        return None


class AbstractCollector(_CollectorLifecycleMixin, ABC):
    """
    Structured collector: stable ``name``, ``validate_config``, then ``collect``.

    :meth:`run` calls ``validate_config`` then ``collect`` so management commands
    keep using :class:`core.collectors.command_base.BaseCollectorCommand` unchanged.

    Override :meth:`handle_error` only when :func:`classify_failure` does not map your
    domain errors cleanly; logs still use :class:`CollectorFailureCategory` values.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Stable collector id for logs and metrics (e.g. app or command slug).

        Returns:
            Non-empty string used as the ``collector`` field in structured logs when
            :meth:`handle_error` runs.
        """

    @abstractmethod
    def validate_config(self) -> None:
        """
        Validate settings and environment before :meth:`collect`.

        Returns:
            None

        Raises:
            Exception: Typically validation-related errors; should not perform
                heavy I/O—keep that in :meth:`collect` via services.
        """

    @abstractmethod
    def collect(self) -> None:
        """
        Main collection work (fetch, transform, persist).

        Returns:
            None

        Raises:
            Exception: Domain failures; propagate after logging when run under
                :class:`~core.collectors.command_base.BaseCollectorCommand`.

        Note:
            DB writes should go through the app's ``services.py`` module per project
            conventions.
        """

    def run(self) -> None:
        self.validate_config()
        self.collect()
