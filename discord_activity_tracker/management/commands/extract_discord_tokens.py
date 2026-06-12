"""
Management command: extract_discord_tokens

Persist Discord session credentials to workspace JSON.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from discord_activity_tracker.utils.discord_internal_tokens_store import (
    discord_internal_tokens_json_path,
    extract_and_save_discord_internal_tokens,
)
from discord_activity_tracker.utils.discord_tokens import (
    _resolve_discord_chrome_profile_root,
)
from discord_activity_tracker.workspace import get_chrome_profile_path

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Persist Discord session credentials to "
        "workspace/discord_activity_tracker/discord_internal_tokens.json."
    )

    def handle(self, *args, **options):
        allow_raw = getattr(settings, "ALLOW_INTERNAL_DISCORD_TOKENS", "") or ""
        if isinstance(allow_raw, bool):
            allow = allow_raw
        else:
            allow = str(allow_raw).strip().lower() == "true"
        if not allow:
            self.stderr.write(
                self.style.WARNING(
                    "Internal Discord session mode is not enabled: credentials will be saved to "
                    "workspace JSON but ignored by Django until enabled. "
                    "Restart web/celery after enabling. See .env.example."
                )
            )

        try:
            profile = _resolve_discord_chrome_profile_root()
        except ValueError as e:
            raise CommandError(str(e)) from e
        profile_path = str(profile)
        if not profile.is_dir():
            raise CommandError(
                "Session storage not found "
                f"({profile_path}). Expected: {get_chrome_profile_path()}. "
                "See .env.example."
            )

        token = extract_and_save_discord_internal_tokens()
        if not token:
            raise CommandError("Failed to load session credentials. See .env.example.")
        out_path = discord_internal_tokens_json_path()
        self.stdout.write(
            self.style.SUCCESS(f"Saved Discord session credentials to {out_path}.")
        )
