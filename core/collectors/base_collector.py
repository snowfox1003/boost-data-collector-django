"""
Structured collector contract: ``name``, ``validate_config``, ``collect``.

:class:`AbstractCollector` composes with :class:`core.collectors.base.CollectorBase`
via a shared lifecycle mixin (``handle_error`` / ``sync_pinecone``) so
:class:`core.collectors.command_base.BaseCollectorCommand` stays unchanged.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from core.errors import classify_failure

logger = logging.getLogger(__name__)


@runtime_checkable
class CollectorRunnable(Protocol):
    """Collector instance with ``run``, ``sync_pinecone``, and ``handle_error`` (see ``BaseCollectorCommand``)."""

    def run(self) -> None: ...

    def sync_pinecone(self) -> None: ...

    def handle_error(self, exc: BaseException) -> None: ...


class _CollectorLifecycleMixin:
    """
    Shared ``handle_error`` / ``sync_pinecone`` for legacy and structured collectors.

    Uses :func:`core.errors.classify_failure` so logs align with
    :class:`core.errors.CollectorFailureCategory`.
    """

    def handle_error(self, exc: BaseException) -> None:
        """Log failures with ``failure_category`` from :class:`CollectorFailureCategory`."""
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
        """Optional post-run Pinecone sync; default is no-op."""
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
        """Stable collector id for logs and metrics (e.g. app or command slug)."""

    @abstractmethod
    def validate_config(self) -> None:
        """Raise or no-op before :meth:`collect`; keep side effects in services."""

    @abstractmethod
    def collect(self) -> None:
        """Main collection work; DB writes belong in ``services.py``."""

    def run(self) -> None:
        self.validate_config()
        self.collect()
