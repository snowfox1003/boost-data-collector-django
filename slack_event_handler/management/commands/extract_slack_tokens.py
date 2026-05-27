"""
Management command: extract_slack_tokens

Reads xoxc/xoxd from CHROME_PROFILE_PATH and saves them to workspace JSON.
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
        "Extract Slack xoxc/xoxd tokens from CHROME_PROFILE_PATH and write "
        "workspace/slack_event_handler/slack_internal_tokens.json. "
        "Stop slack-chromium (slack-session profile) before running to avoid LevelDB locks."
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
                    "ALLOW_INTERNAL_SLACK_TOKENS is not true: tokens will be saved to "
                    "workspace JSON but ignored by Django until enabled. "
                    "Restart web/celery after enabling."
                )
            )

        try:
            profile = _resolve_chrome_profile_root()
        except ValueError as e:
            raise CommandError(str(e)) from e
        profile_path = str(profile)
        if not profile.is_dir():
            raise CommandError(
                "Chrome profile not found at CHROME_PROFILE_PATH "
                f"({profile_path}). Expected: {get_chrome_profile_path()}. "
                "Log into Slack via make slack-login, then re-run extract_slack_tokens."
            )

        pair = extract_and_save_slack_internal_tokens(team_id)
        if not pair:
            raise CommandError(
                "Token extraction failed. Ensure Slack is logged in under "
                f"CHROME_PROFILE_PATH ({profile_path}) and slack-chromium is stopped."
            )
        out_path = slack_internal_tokens_json_path()
        self.stdout.write(
            self.style.SUCCESS(
                f"Extracted tokens for team {team_id}; saved to {out_path}."
            )
        )
