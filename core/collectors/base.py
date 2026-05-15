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
    """
    Legacy abstract base for collectors run via management commands or YAML schedules.

    **Purpose:** Provide a single orchestration hook, :meth:`run`, while sharing
    Pinecone and structured logging behavior with :class:`AbstractCollector` through
    :class:`_CollectorLifecycleMixin`.

    **Subclasses must implement:** :meth:`run` only. For new collectors, prefer
    :class:`AbstractCollector` (``name``, ``validate_config``, ``collect``); its
    concrete :meth:`~AbstractCollector.run` calls those hooks so
    :class:`~core.collectors.command_base.BaseCollectorCommand` stays unchanged.

    **Lifecycle hooks (inherited):** :meth:`~_CollectorLifecycleMixin.sync_pinecone`
    (optional post-run, default no-op) and :meth:`~_CollectorLifecycleMixin.handle_error`
    (structured logging). When the collector is driven by
    :class:`~core.collectors.command_base.BaseCollectorCommand`, attribute
    ``_error_phase`` is set to ``\"run\"`` or ``\"sync_pinecone\"`` for the duration
    of each phase so logs include ``collector_phase``.

    **Error handling contract:** Exceptions other than :class:`django.core.management.base.CommandError`
    are passed to :meth:`~_CollectorLifecycleMixin.handle_error`, which uses
    :func:`core.errors.classify_failure` and ``logger.exception`` with ``failure_category``
    in ``extra``. The original exception is then re-raised. ``CommandError`` is logged
    by the command layer without calling :meth:`~_CollectorLifecycleMixin.handle_error`.
    """

    @abstractmethod
    def run(self) -> None:
        """
        Execute the collector work unit.

        Returns:
            None: Implementations should return implicitly after successful work.

        Note:
            Prefer :class:`AbstractCollector` when splitting validation from
            collection improves clarity; it still satisfies this base's contract via
            its concrete :meth:`~AbstractCollector.run`.
        """


class DjangoCommandCollector(CollectorBase):
    """Runs a registered Django management command by name."""

    __slots__ = ("command_name",)

    def __init__(self, command_name: str) -> None:
        self.command_name = command_name

    def run(self) -> None:
        call_command(self.command_name)
