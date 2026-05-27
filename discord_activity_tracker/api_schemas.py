"""Pydantic models for discord.py API payloads at ingestion boundaries (live sync)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, NoReturn

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DiscordLiveSyncValidationError(ValueError):
    """Discord API payload failed Pydantic validation (live-sync path)."""


class DiscordLiveUserPayload(BaseModel):
    """Normalized author from Bot API or exporter-shaped dict."""

    model_config = ConfigDict(extra="allow")

    user_id: int
    username: str = "unknown"
    display_name: str = ""
    avatar_url: str = ""
    is_bot: bool = False


class DiscordReactionPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    discord_message_id: int
    emoji: str = Field(min_length=1)
    count: int = Field(default=0, ge=0)


class DiscordLivePreparedMessage(BaseModel):
    """Output of ``_prepare_message_data`` for bulk DB upsert."""

    model_config = ConfigDict(extra="allow")

    message_id: int
    author: DiscordLiveUserPayload
    content: str = ""
    message_type: str = "Default"
    is_pinned: bool = False
    message_created_at: datetime
    message_edited_at: datetime | None = None
    reply_to_message_id: int | None = None
    attachment_urls: list[str] = Field(default_factory=list)
    reactions: list[Any] = Field(default_factory=list)


def _validation_error(prefix: str, err: ValidationError) -> NoReturn:
    detail = err.errors()[:5]
    msg = f"{prefix}: " + "; ".join(
        f"{e.get('loc', ())}: {e.get('msg', '')}" for e in detail
    )
    if len(err.errors()) > 5:
        msg += f" … ({len(err.errors())} errors total)"
    raise DiscordLiveSyncValidationError(msg) from err


def parse_live_user(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> DiscordLiveUserPayload:
    prefix = f"Invalid Discord live user{f' ({source})' if source else ''}"
    try:
        return DiscordLiveUserPayload.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_live_message(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> DiscordLivePreparedMessage:
    prefix = f"Invalid Discord live message{f' ({source})' if source else ''}"
    try:
        return DiscordLivePreparedMessage.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_reaction(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> DiscordReactionPayload:
    prefix = f"Invalid Discord reaction{f' ({source})' if source else ''}"
    try:
        return DiscordReactionPayload.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)
