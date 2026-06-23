"""
Structured collector contract: ``name``, ``validate_config``, ``collect``.

:class:`AbstractCollector` uses :class:`_CollectorLifecycleMixin` for
``pre_collect`` / ``post_collect`` / ``on_error`` / ``handle_error`` / ``sync_pinecone``
so :class:`core.collectors.command_base.BaseCollectorCommand` can invoke ``run`` then
``sync_pinecone`` unchanged.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Protocol, runtime_checkable

from core.errors import classify_failure, sanitize_exception_message
from core.protocols import (
    IncrementalState,
    TrackerResult,
    require_incremental_state,
    require_tracker_result,
)
from core.tracker_result import with_duration_if_missing

logger = logging.getLogger(__name__)


def _safe_exc_info(
    exc: BaseException,
) -> bool | tuple[type[BaseException], BaseException, TracebackType | None]:
    """Build logging ``exc_info`` with a redacted exception message when needed."""
    safe_msg = sanitize_exception_message(exc)
    if safe_msg == str(exc):
        return True
    try:
        safe_exc = type(exc)(safe_msg)
    except (TypeError, ValueError):
        safe_exc = RuntimeError(safe_msg)
        safe_exc.__cause__ = None
        safe_exc.__suppress_context__ = True
    if exc.__traceback__ is not None:
        safe_exc.__traceback__ = exc.__traceback__
    return (type(safe_exc), safe_exc, exc.__traceback__)


@runtime_checkable
class CollectorRunnable(Protocol):
    """
    Structural type for objects executed by :class:`BaseCollectorCommand`.

    Implementations are typically :class:`AbstractCollector` subclasses (or any object
    satisfying this protocol). The command invokes :meth:`run`, then :meth:`sync_pinecone`, and
    routes failures through :meth:`handle_error` (except :class:`~django.core.management.base.CommandError`).
    """

    def run(self) -> TrackerResult:
        """Main collection phase; see :class:`AbstractCollector`."""
        ...

    def sync_pinecone(self) -> None:
        """Optional post-run sync; may be a no-op."""
        ...

    def handle_error(self, exc: BaseException) -> None:
        """Log *exc* with structured ``failure_category``; must not swallow *exc*."""
        ...

    @property
    def last_result(self) -> TrackerResult | None:
        """Outcome of the most recent successful :meth:`run`, if any."""
        ...


class _CollectorLifecycleMixin:
    """
    Shared lifecycle hooks for collector implementations.

    Override points: :meth:`pre_collect`, :meth:`post_collect`, :meth:`on_error`,
    :meth:`handle_error`, :meth:`sync_pinecone`. Defaults are no-ops except
    :meth:`handle_error`, which logs via :func:`core.errors.classify_failure`.

    **``_error_phase``:** Set only by :class:`~core.collectors.command_base.BaseCollectorCommand`
    around each phase; used when logging. If :func:`~core.errors.classify_failure`
    or logging raises, the command's ``finally`` still clears ``_error_phase`` on the
    collector instance.

    **Intentional gaps:** Many domain or SDK exceptions map to ``unknown``. Override
    :meth:`handle_error` when you need a different category or extra context.
    """

    _last_result: TrackerResult | None
    _incremental_state_in: IncrementalState | None
    _incremental_state_out: IncrementalState | None

    def pre_collect(self) -> None:
        """
        Optional setup before :meth:`~AbstractCollector.validate_config`.

        Use for incremental state checks, backlog processing, or startup logging.
        Default is no-op.

        Returns:
            None
        """
        return None

    def post_collect(self) -> None:
        """
        Optional teardown or reporting after :meth:`~AbstractCollector.collect` succeeds.

        Default persists :attr:`_incremental_state_out` when set.

        Returns:
            None
        """
        state_out = getattr(self, "_incremental_state_out", None)
        if state_out is not None:
            self.persist_incremental_state(require_incremental_state(state_out))
        return None

    def load_incremental_state(self) -> IncrementalState | None:
        """Load checkpoint from DB/workspace; override in incremental collectors."""
        return None

    def persist_incremental_state(self, state: IncrementalState) -> None:
        """Persist checkpoint after a successful run; override in incremental collectors."""
        return None

    def on_error(self, exc: BaseException) -> None:
        """
        Optional collector-specific error hook when :meth:`~AbstractCollector.run` fails.

        Args:
            exc: The exception from a step inside :meth:`~AbstractCollector.run`.
                Must not be swallowed — :meth:`run` always re-raises after this hook.

        Returns:
            None
        """
        return None

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
            exc_info=_safe_exc_info(exc),
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

    @property
    def last_result(self) -> TrackerResult | None:
        """Outcome of the most recent successful :meth:`run`, if any."""
        return getattr(self, "_last_result", None)


class AbstractCollector(_CollectorLifecycleMixin, ABC):
    """
    Structured collector: stable ``name``, lifecycle hooks, then ``collect``.

    :meth:`run` orchestrates ``pre_collect`` → ``validate_config`` → ``collect`` →
    ``post_collect``. On failure, :meth:`on_error` runs then the exception propagates.
    Management commands use :class:`core.collectors.command_base.BaseCollectorCommand`
    to call :meth:`run` then :meth:`sync_pinecone`.

    Hook responsibilities:

    - ``validate_config()`` — light env/CLI checks only (no heavy I/O).
    - ``pre_collect()`` — pre-fetch, incremental state, startup logging.
    - ``collect()`` — main fetch/transform/persist work (via services).
    - ``post_collect()`` — summary stdout, metrics, non-Pinecone teardown.
    - ``on_error(exc)`` — partial-state cleanup; must not swallow *exc*.
    - ``sync_pinecone()`` — vector sync after successful :meth:`run` (command layer).

    Do not override :meth:`run`. Override :meth:`handle_error` only when
    :func:`classify_failure` does not map your domain errors cleanly.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

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
                heavy I/O—keep that in :meth:`pre_collect` or :meth:`collect` via services.
        """

    @abstractmethod
    def collect(self) -> TrackerResult:
        """
        Main collection work (fetch, transform, persist).

        Returns:
            A :class:`~core.protocols.TrackerResult` describing the run outcome.

        Raises:
            Exception: Domain failures; propagate after logging when run under
                :class:`~core.collectors.command_base.BaseCollectorCommand`.

        Note:
            DB writes should go through the app's ``services.py`` module per project
            conventions.
        """

    def run(self) -> TrackerResult:
        self._incremental_state_in = None
        self._incremental_state_out = None
        started = time.monotonic()
        try:
            self.pre_collect()
            self.validate_config()
            loaded_state = self.load_incremental_state()
            self._incremental_state_in = (
                require_incremental_state(loaded_state)
                if loaded_state is not None
                else None
            )
            raw_result = self.collect()
            result = require_tracker_result(raw_result)
            elapsed = time.monotonic() - started
            result = with_duration_if_missing(result, elapsed)
            self.post_collect()
            self._last_result = result
            return result
        except Exception as exc:
            try:
                self.on_error(exc)
            except Exception:
                collector_id = getattr(self, "name", None)
                if not isinstance(collector_id, str) or not collector_id:
                    collector_id = self.__class__.__name__
                logger.exception(
                    "Collector on_error hook failed: collector=%s",
                    collector_id,
                )
            raise
