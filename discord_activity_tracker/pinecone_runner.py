"""Shared Pinecone upsert via ``run_cppa_pinecone_sync`` for Discord commands."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.management import call_command

logger = logging.getLogger(__name__)

DISCORD_PINECONE_PREPROCESSOR = (
    "discord_activity_tracker.preprocessor.preprocess_discord_for_pinecone"
)


def task_discord_pinecone_sync(*, dry_run: bool = False) -> None:
    """Upsert Discord messages to Pinecone using settings (mirrors Boost tracker pattern)."""
    logger.info("Pinecone upsert (Discord messages)")
    if dry_run:
        logger.info("dry-run would run Pinecone sync for Discord messages")
        return

    app_type = (getattr(settings, "PINECONE_DISCORD_APP_TYPE", "") or "").strip()
    namespace = (getattr(settings, "PINECONE_DISCORD_NAMESPACE", "") or "").strip()
    if not app_type:
        logger.warning(
            "Pinecone sync skipped: PINECONE_DISCORD_APP_TYPE is empty (settings/env)."
        )
        return
    if not namespace:
        logger.warning(
            "Pinecone sync skipped: PINECONE_DISCORD_NAMESPACE is empty (settings/env)."
        )
        return

    try:
        call_command(
            "run_cppa_pinecone_sync",
            app_type=app_type,
            namespace=namespace,
            preprocessor=DISCORD_PINECONE_PREPROCESSOR,
        )
        logger.info(
            "pinecone sync completed (app_type=%s, namespace=%s)",
            app_type,
            namespace,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Pinecone sync skipped/failed (run_cppa_pinecone_sync unavailable or errored): %s",
            exc,
        )
