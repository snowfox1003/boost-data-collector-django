"""DiscordChatExporter date-window helpers (scheduled sync + backfill)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def latest_message_created_at_for_channel(
    guild_snowflake: int,
    channel_snowflake: int,
) -> datetime | None:
    """Latest ``message_created_at`` for one channel (non-deleted messages)."""
    return DiscordMessage.objects.filter(
        channel__server__server_id=guild_snowflake,
        channel__channel_id=channel_snowflake,
        is_deleted=False,
    ).aggregate(m=Max("message_created_at"))["m"]


def incremental_export_after(latest: datetime) -> datetime:
    """Lower bound for the next scheduled export with overlap.

    Returns UTC midnight on the calendar day of *latest* so the full day is
    re-exported. Duplicate messages are merged by snowflake id; gaps are not.
    """
    return utc_day_start(latest)


def resolve_channel_export_after(
    guild_snowflake: int,
    channel_snowflake: int,
    *,
    explicit_after: datetime | None,
) -> datetime | None:
    """Per-channel ``--after`` for DiscordChatExporter.

    When *explicit_after* is set (``--since``), it applies to every channel.
    Otherwise resumes from the UTC day start of that channel's latest stored
    message, or ``None`` when the channel has no rows (today-only export).
    """
    if explicit_after is not None:
        return explicit_after
    latest = latest_message_created_at_for_channel(
        guild_snowflake,
        channel_snowflake,
    )
    if latest is None:
        return None
    return incremental_export_after(latest)


def utc_day_start(dt: datetime) -> datetime:
    """UTC midnight for the calendar day containing *dt*."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def iter_channel_export_days(
    *,
    after: datetime | None,
    before: datetime | None,
    now: datetime | None = None,
) -> list[tuple[str, datetime, datetime]]:
    """Build per-day UTC export windows for DiscordChatExporter.

    Returns ``(YYYY-MM-DD, window_after, window_before)`` in chronological order.

    - When *after* is ``None`` (empty DB, no ``--since``): **today only** (UTC).
    - Otherwise: from ``floor(after)`` through ``floor(before or now)`` inclusive.
    - Each window is clipped to ``[max(day_start, after), min(day_end, before or now)]``.
    - Skips days where the clipped window is empty (``after >= before``).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    upper = now
    if before is not None:
        upper = (
            before.astimezone(timezone.utc)
            if before.tzinfo is not None
            else before.replace(tzinfo=timezone.utc)
        )

    if after is None:
        first_day = utc_day_start(now)
        last_day = first_day
    else:
        after_utc = (
            after.astimezone(timezone.utc)
            if after.tzinfo is not None
            else after.replace(tzinfo=timezone.utc)
        )
        first_day = utc_day_start(after_utc)
        last_day = utc_day_start(upper)

    after_utc: datetime | None = None
    if after is not None:
        after_utc = (
            after.astimezone(timezone.utc)
            if after.tzinfo is not None
            else after.replace(tzinfo=timezone.utc)
        )

    before_utc: datetime | None = None
    if before is not None:
        before_utc = (
            before.astimezone(timezone.utc)
            if before.tzinfo is not None
            else before.replace(tzinfo=timezone.utc)
        )

    result: list[tuple[str, datetime, datetime]] = []
    day = first_day
    while day <= last_day:
        day_end = day + timedelta(days=1)
        window_after = day
        window_before = day_end

        if after_utc is not None and day == first_day:
            window_after = max(day, after_utc)
        if before_utc is not None and day == last_day:
            window_before = min(day_end, before_utc)
        elif before is None and day == last_day:
            window_before = min(day_end, now)

        if window_after < window_before:
            result.append((day.strftime("%Y-%m-%d"), window_after, window_before))
        day += timedelta(days=1)

    return result
