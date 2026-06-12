"""
Management command: extract_slack_tokens

Persist Slack session credentials to workspace JSON.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.operations.slack_ops.tokens import get_default_team_key
from slack_event_handler.utils.slack_internal_tokens_store import (
    extract_and_save_slack_internal_tokens,
    slack_internal_tokens_json_path,
)
from slack_event_handler.utils.slack_tokens import _resolve_chrome_profile_root
from slack_event_handler.workspace import get_chrome_profile_path

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Persist Slack session credentials to "
        "workspace/slack_event_handler/slack_internal_tokens.json."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--team-id",
            dest="team_id",
            default=None,
            help="Slack team ID (default: first team from SLACK_TEAM_IDS).",
        )

    def handle(self, *args, **options):
        team_id = (options.get("team_id") or "").strip() or get_default_team_key()
        if not team_id:
            raise CommandError(
                "No team id. Pass --team-id or set SLACK_TEAM_IDS in .env."
            )

        allow_raw = getattr(settings, "ALLOW_INTERNAL_SLACK_TOKENS", "") or ""
        if isinstance(allow_raw, bool):
            allow = allow_raw
        else:
            allow = str(allow_raw).strip().lower() == "true"
        if not allow:
            self.stderr.write(
                self.style.WARNING(
                    "Internal Slack session mode is not enabled: credentials will be saved to "
                    "workspace JSON but ignored by Django until enabled. "
                    "Restart web/celery after enabling. See .env.example."
                )
            )

        try:
            profile = _resolve_chrome_profile_root()
        except ValueError as e:
            raise CommandError(str(e)) from e
        profile_path = str(profile)
        if not profile.is_dir():
            raise CommandError(
                "Session storage not found "
                f"({profile_path}). Expected: {get_chrome_profile_path()}. "
                "See .env.example."
            )

        pair = extract_and_save_slack_internal_tokens(team_id)
        if not pair:
            raise CommandError("Failed to load session credentials. See .env.example.")
        out_path = slack_internal_tokens_json_path()
        self.stdout.write(
            self.style.SUCCESS(
                f"Saved session credentials for team {team_id} to {out_path}."
            )
        )
