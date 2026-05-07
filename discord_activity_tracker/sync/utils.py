"""Helpers for Discord sync."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime."""
    if not date_str:
        return None

    try:
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError) as e:
        logger.debug(f"Failed to parse datetime '{date_str}': {e}")
        return None


def parse_discord_user(user_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize user dict from Bot API or DiscordChatExporter.

    Handles both sources:
    - Bot API: keys ``id`` (int), ``username``, ``display_name``, ``avatar_url``, ``bot``
    - DiscordChatExporter: keys ``id`` (str), ``name``, ``nickname``, ``avatarUrl``, ``isBot``
    All snowflake IDs are coerced to int.
    """
    if not user_data:
        return {
            "user_id": 0,
            "username": "unknown",
            "display_name": "",
            "avatar_url": "",
            "is_bot": False,
        }

    raw_id = user_data.get("id", 0)
    try:
        user_id = int(raw_id) if raw_id is not None else 0
    except (TypeError, ValueError):
        user_id = 0

    # avatar_url: Bot API uses "avatar_url"; DiscordChatExporter uses "avatarUrl"
    avatar_url = user_data.get("avatar_url") or user_data.get("avatarUrl") or ""

    return {
        "user_id": user_id,
        "username": user_data.get("username") or user_data.get("name") or "unknown",
        "display_name": (
            user_data.get("display_name")
            or user_data.get("global_name")
            or user_data.get("nickname")
            or ""
        ),
        "avatar_url": avatar_url,
        "is_bot": bool(user_data.get("bot") or user_data.get("isBot", False)),
    }


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


def truncate_content(content: str, max_length: int = 100) -> str:
    """Truncate with ellipsis."""
    if len(content) <= max_length:
        return content
    return content[: max_length - 3] + "..."
