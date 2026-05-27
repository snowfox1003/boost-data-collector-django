"""Tests for core.collectors base types."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management.base import CommandError

import core.collectors.base_collector as collector_lifecycle
from core.collectors.base_collector import AbstractCollector
from core.collectors.command_base import BaseCollectorCommand


class _CallCommandCollector(AbstractCollector):
    """Invokes ``call_command`` from :meth:`collect` (tests adapter-style collectors)."""

    __slots__ = ("_command_name",)

    def __init__(self, command_name: str) -> None:
        self._command_name = command_name

    @property
    def name(self) -> str:
        return "call_command_adapter"

    def validate_config(self) -> None:
        return None

    def collect(self) -> None:
        from django.core.management import call_command as _call_command

        _call_command(self._command_name)


def test_call_command_collector_collect_invokes_call_command():
    with patch("django.core.management.call_command") as m:
        c = _CallCommandCollector("run_boost_usage_tracker")
        c.collect()
    m.assert_called_once_with("run_boost_usage_tracker")


def test_call_command_collector_sync_pinecone_default_noop():
    c = _CallCommandCollector("check")
    assert c.sync_pinecone() is None


def test_base_collector_command_runs_then_sync_pinecone():
    phases = []

    class OkCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "ok"

        def validate_config(self) -> None:
            return None

        def collect(self) -> None:
            phases.append("run")

        def sync_pinecone(self) -> None:
            phases.append("sync")

    class Cmd(BaseCollectorCommand):
        help = "test"

        def get_collector(self, **options):
            return OkCollector()

    Cmd(stdout=StringIO(), stderr=StringIO()).handle()
    assert phases == ["run", "sync"]


def test_base_collector_command_propagates_command_error():
    class BadCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "bad"

        def validate_config(self) -> None:
            return None

        def collect(self) -> None:
            raise CommandError("planned", returncode=3)

    class Cmd(BaseCollectorCommand):
        help = "test"

        def get_collector(self, **options):
            return BadCollector()

    with pytest.raises(CommandError, match="planned"):
        Cmd(stdout=StringIO(), stderr=StringIO()).handle()


def test_abstract_collector_handle_error_logs_failure_category():
    class PhaseCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "phase"

        def validate_config(self) -> None:
            return None

        def collect(self) -> None:
            return None

    collector = PhaseCollector()
    collector._error_phase = "fetch"

    with patch.object(collector_lifecycle.logger, "exception") as mock_exc:
        collector.handle_error(RuntimeError("boom"))

    mock_exc.assert_called_once()
    assert "phase" in str(mock_exc.call_args)


def test_base_collector_command_logs_and_reraises_generic_exception():
    class BadCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "bad"

        def validate_config(self) -> None:
            return None

        def collect(self) -> None:
            raise RuntimeError("boom")

    class Cmd(BaseCollectorCommand):
        help = "test"

        def get_collector(self, **options):
            return BadCollector()

    with patch.object(BadCollector, "handle_error") as mock_handle:
        with pytest.raises(RuntimeError, match="boom"):
            Cmd(stdout=StringIO(), stderr=StringIO()).handle()
    mock_handle.assert_called_once()
    assert isinstance(mock_handle.call_args[0][0], RuntimeError)


def test_base_collector_command_requires_get_collector_at_instantiation():
    class IncompleteCmd(BaseCollectorCommand):
        help = "test"

    with pytest.raises(TypeError, match="get_collector"):
        IncompleteCmd(stdout=StringIO(), stderr=StringIO())


def test_base_collector_command_failure_classifies_in_handle_error():
    class BadCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "bad"

        def validate_config(self) -> None:
            return None

        def collect(self) -> None:
            raise ValueError("bad input")

    class Cmd(BaseCollectorCommand):
        help = "test"

        def get_collector(self, **options):
            return BadCollector()

    with patch.object(collector_lifecycle.logger, "exception") as mock_exc:
        with pytest.raises(ValueError, match="bad input"):
            Cmd(stdout=StringIO(), stderr=StringIO()).handle()
    mock_exc.assert_called_once()
    assert mock_exc.call_args[1]["extra"]["failure_category"] == "validation"


def test_base_collector_command_double_fault_clears_error_phase():
    class BadCollector(AbstractCollector):
        @property
        def name(self) -> str:
            return "bad"

        def validate_config(self) -> None:
            return None

        def collect(self) -> None:
            raise RuntimeError("primary")

    held: dict[str, AbstractCollector] = {}

    class Cmd(BaseCollectorCommand):
        help = "test"

        def get_collector(self, **options):
            c = BadCollector()
            held["c"] = c
            return c

    cmd = Cmd(stdout=StringIO(), stderr=StringIO())
    with patch.object(
        BadCollector,
        "handle_error",
        side_effect=AssertionError("secondary"),
    ):
        with pytest.raises(AssertionError, match="secondary"):
            cmd.handle()
    assert not hasattr(held["c"], "_error_phase")


def test_abstract_collector_run_calls_validate_then_collect():
    order = []

    class AC(AbstractCollector):
        @property
        def name(self) -> str:
            return "ac_test"

        def validate_config(self) -> None:
            order.append("validate")

        def collect(self) -> None:
            order.append("collect")

    AC().run()
    assert order == ["validate", "collect"]


def test_abstract_collector_handle_error_uses_name_in_log_extra():
    class Named(AbstractCollector):
        @property
        def name(self) -> str:
            return "named_slug"

        def validate_config(self) -> None:
            pass

        def collect(self) -> None:
            pass

    c = Named()
    c._error_phase = "collect"
    with patch.object(collector_lifecycle.logger, "exception") as mock_exc:
        c.handle_error(RuntimeError("x"))
    mock_exc.assert_called_once()
    assert "named_slug" in str(mock_exc.call_args)
