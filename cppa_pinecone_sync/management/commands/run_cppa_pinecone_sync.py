"""
Management command: run_cppa_pinecone_sync

Runs Pinecone sync for a single (app_type, namespace, preprocessor) when invoked
with all three parameters (e.g. by another app or scheduler).

Usage:
    python manage.py run_cppa_pinecone_sync --app-type slack --namespace slack-Cpplang --preprocessor myapp.preprocessors.slack_preprocess
    python manage.py run_cppa_pinecone_sync   # no args: hint only (run-all not yet implemented)
"""

from __future__ import annotations

import argparse
import importlib
import logging
from typing import Any, cast

from django.core.management.base import CommandError

from core.collectors import AbstractCollector, BaseCollectorCommand
from core.protocols import TrackerResult

from cppa_pinecone_sync.protocol_impl import PineconeSyncTrackerResult
from cppa_pinecone_sync.sync import PreprocessFn, sync_to_pinecone
from cppa_pinecone_sync.types import PineconeInstance

logger = logging.getLogger(__name__)


def _resolve_preprocessor(dotted_path: str) -> PreprocessFn:
    """Resolve a dotted path (e.g. 'myapp.preprocessors.slack_preprocess') to a callable."""
    if "." not in dotted_path:
        raise ValueError(
            "Preprocessor must be a dotted path to a callable, e.g. 'myapp.preprocessors.slack_preprocess'"
        )
    module_path, _, name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    fn = getattr(module, name, None)
    if fn is None:
        raise ValueError(f"Module {module_path!r} has no attribute {name!r}")
    if not callable(fn):
        raise ValueError(f"{dotted_path!r} is not callable")
    return cast(PreprocessFn, fn)


class CppaPineconeSyncCollector(AbstractCollector):
    """Run sync_to_pinecone for one (app_type, namespace, preprocessor)."""

    def __init__(
        self,
        *,
        app_type: str,
        namespace: str,
        preprocessor_path: str,
        instance: PineconeInstance,
    ) -> None:
        self.app_type = app_type
        self.namespace = namespace
        self.preprocessor_path = preprocessor_path
        self.instance = instance
        self._preprocess_fn: PreprocessFn | None = None

    @property
    def name(self) -> str:
        return "cppa_pinecone_sync"

    def validate_config(self) -> None:
        try:
            self._preprocess_fn = _resolve_preprocessor(self.preprocessor_path)
        except (ValueError, ImportError) as e:
            raise CommandError(str(e)) from e

    def collect(self) -> TrackerResult:
        logger.info(
            "run_cppa_pinecone_sync: starting app_type=%s namespace=%s preprocessor=%s",
            self.app_type,
            self.namespace,
            self.preprocessor_path,
        )

        preprocess_fn = self._preprocess_fn
        if preprocess_fn is None:
            raise CommandError("Preprocessor not resolved; call validate_config first")

        raw = sync_to_pinecone(
            self.app_type,
            self.namespace,
            preprocess_fn,
            instance=self.instance,
        )
        result = PineconeSyncTrackerResult.from_sync_dict(raw)
        logger.info(
            "CPPA Pinecone Sync completed: upserted=%s, total=%s, failed_count=%s",
            result.counts.get("upserted", 0),
            result.counts.get("total", 0),
            result.counts.get("failed_count", 0),
        )
        for err in result.errors:
            logger.warning("Sync error: %s", err)
        logger.info("run_cppa_pinecone_sync: finished successfully")
        return result


class Command(BaseCollectorCommand):
    help = (
        "Run CPPA Pinecone Sync. Pass --app-type, --namespace and --preprocessor to run "
        "sync_to_pinecone for one source; other apps can call sync_to_pinecone() directly."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--app-type",
            type=str,
            default=None,
            help="App type (e.g. 'slack', 'mailing'). Required with --namespace and --preprocessor.",
        )
        parser.add_argument(
            "--namespace",
            type=str,
            default=None,
            help="Pinecone namespace to upsert into. Required when --app-type is set.",
        )
        parser.add_argument(
            "--preprocessor",
            type=str,
            default=None,
            help="Dotted path to preprocess function (e.g. 'myapp.preprocessors.slack_preprocess'). Required when --app-type is set.",
        )
        parser.add_argument(
            "--pinecone-instance",
            type=str,
            choices=[i.value for i in PineconeInstance],
            default=PineconeInstance.PUBLIC.value,
            help="Pinecone API key instance to use: 'public' (default) or 'private'.",
        )

    def get_collector(self, **options: Any) -> AbstractCollector:
        app_type = (options.get("app_type") or "").strip() or None
        namespace = (options.get("namespace") or "").strip() or None
        preprocessor_path = (options.get("preprocessor") or "").strip() or None
        instance = PineconeInstance(
            (options.get("pinecone_instance") or PineconeInstance.PUBLIC.value).strip()
        )

        if app_type is not None and not (namespace and preprocessor_path):
            raise CommandError(
                "When --app-type is set, both --namespace and --preprocessor are required."
            )
        if (namespace or preprocessor_path) and app_type is None:
            raise CommandError(
                "When --namespace or --preprocessor is set, --app-type is required."
            )

        if app_type is None:
            raise CommandError(
                "No --app-type/--namespace/--preprocessor given. "
                "Run with --app-type, --namespace and --preprocessor to sync one source; "
                "or register sources and run 'all' (not yet implemented)."
            )

        return CppaPineconeSyncCollector(
            app_type=app_type,
            namespace=namespace or "",
            preprocessor_path=preprocessor_path or "",
            instance=instance,
        )
