"""DiscordChatExporter date-window helpers (scheduled sync + backfill)."""

from __future__ import annotations

from datetime import datetime

from django.db.models import Max

from discord_activity_tracker.models import DiscordMessage


def latest_message_created_at_for_guild(
    guild_snowflake: int,
    *,
    channel_ids: list[int] | None,
) -> datetime | None:
    """Latest ``message_created_at`` for non-deleted messages (optional channel scope)."""
    qs = DiscordMessage.objects.filter(
        channel__server__server_id=guild_snowflake,
        is_deleted=False,
    )
    if channel_ids:
        qs = qs.filter(channel__channel_id__in=channel_ids)
    return qs.aggregate(m=Max("message_created_at"))["m"]
