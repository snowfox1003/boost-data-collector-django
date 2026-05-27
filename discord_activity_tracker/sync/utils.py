"""Helpers for Discord sync."""

from typing import Any, Optional

from discord_activity_tracker.api_schemas import DiscordLiveUserPayload


def parse_discord_user(user_data: Optional[dict[str, Any]]) -> DiscordLiveUserPayload:
    """Normalize user dict from Bot API or DiscordChatExporter.

    Handles both sources:
    - Bot API: keys ``id`` (int), ``username``, ``display_name``, ``avatar_url``, ``bot``
    - DiscordChatExporter: keys ``id`` (str), ``name``, ``nickname``, ``avatarUrl``, ``isBot``
    All snowflake IDs are coerced to int.
    """
    if not user_data:
        return DiscordLiveUserPayload(
            user_id=0,
            username="unknown",
            display_name="",
            avatar_url="",
            is_bot=False,
        )

    raw_id = user_data.get("id", 0)
    try:
        user_id = int(raw_id) if raw_id is not None else 0
    except (TypeError, ValueError):
        user_id = 0

    avatar_url = user_data.get("avatar_url") or user_data.get("avatarUrl") or ""

    return DiscordLiveUserPayload(
        user_id=user_id,
        username=user_data.get("username") or user_data.get("name") or "unknown",
        display_name=(
            user_data.get("display_name")
            or user_data.get("global_name")
            or user_data.get("nickname")
            or ""
        ),
        avatar_url=avatar_url,
        is_bot=bool(user_data.get("bot") or user_data.get("isBot", False)),
    )


def sanitize_channel_name(channel_name: str) -> str:
    """Make channel name safe for use in filenames."""
    safe_name = channel_name.replace("/", "-").replace("\\", "-")
    safe_name = safe_name.replace(":", "-").replace("*", "-")
    safe_name = safe_name.replace("?", "").replace('"', "")
    safe_name = safe_name.replace("<", "").replace(">", "")
    safe_name = safe_name.replace("|", "-")
    return safe_name.strip()


def format_discord_url(server_id: int, channel_id: int, message_id: int) -> str:
    """Build Discord message URL."""
    return f"https://discord.com/channels/{server_id}/{channel_id}/{message_id}"
