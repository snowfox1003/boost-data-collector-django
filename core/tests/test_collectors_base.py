"""Tests for core.collectors base types."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management.base import CommandError

import core.collectors.base as collector_base
from core.collectors.base import CollectorBase, DjangoCommandCollector
from core.collectors.command_base import BaseCollectorCommand


@pytest.mark.django_db
def test_django_command_collector_run_calls_call_command():
    with patch("core.collectors.base.call_command") as m:
        c = DjangoCommandCollector("run_boost_usage_tracker")
        c.run()
    m.assert_called_once_with("run_boost_usage_tracker")


def test_django_command_collector_sync_pinecone_default_noop():
    c = DjangoCommandCollector("check")
    assert c.sync_pinecone() is None


def test_base_collector_command_runs_then_sync_pinecone():
    phases = []

    class OkCollector(CollectorBase):
        def run(self) -> None:
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
    class BadCollector(CollectorBase):
        def run(self) -> None:
            raise CommandError("planned", returncode=3)

    class Cmd(BaseCollectorCommand):
        help = "test"

        def get_collector(self, **options):
            return BadCollector()

    with pytest.raises(CommandError, match="planned"):
        Cmd(stdout=StringIO(), stderr=StringIO()).handle()


def test_collector_base_handle_error_logs_failure_category():
    class PhaseCollector(CollectorBase):
        def run(self) -> None:
            pass

    collector = PhaseCollector()
    collector._error_phase = "fetch"

    with patch.object(collector_base.logger, "exception") as mock_exc:
        collector.handle_error(RuntimeError("boom"))

    mock_exc.assert_called_once()
    assert "PhaseCollector" in str(mock_exc.call_args)


def test_base_collector_command_logs_and_reraises_generic_exception():
    class BadCollector(CollectorBase):
        def run(self) -> None:
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
