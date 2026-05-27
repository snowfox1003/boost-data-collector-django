"""Service layer for Discord Activity Tracker.

All writes to ``discord_activity_tracker`` models go through this module (single
writer policy). Higher-level API tables and narrative docs live in
``docs/service_api/discord_activity_tracker.md``.

Bulk ingest expects dicts shaped like the output of
``discord_activity_tracker.sync.messages._prepare_message_data`` or
``discord_activity_tracker.sync.chat_exporter.convert_exporter_message_to_dict``
(normalized message payloads with ``author``, ``message_id``, ``reactions``, etc.).

**CollectorFailureCategory:** These functions perform database I/O only; they do
not call Discord HTTP APIs and do not assign ``CollectorFailureCategory`` labels.
Collectors and sync code classify failures via ``core.errors.classify_failure``.
If a caller logs ORM failures through that helper, mapping follows ``core.errors``.

This module does not intentionally raise ``ValueError`` for bad inputs; bulk
paths may skip individual rows and log warnings (see each function's side effects).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from django.db import transaction
from django.db.models import Max, QuerySet
from django.utils import timezone as django_timezone

from cppa_user_tracker.models import DiscordProfile
from cppa_user_tracker.services import get_or_create_discord_profile
from .api_schemas import (
    DiscordLivePreparedMessage,
    DiscordLiveUserPayload,
    DiscordReactionPayload,
    parse_reaction,
)
from .models import (
    DiscordServer,
    DiscordChannel,
    DiscordMessage,
    DiscordReaction,
)

logger = logging.getLogger(__name__)


def get_or_create_discord_server(
    server_id: int, server_name: str, icon_url: str = ""
) -> Tuple[DiscordServer, bool]:
    """Get or create a Discord guild (server) row and refresh metadata when it already exists.

    Uses ``get_or_create`` on ``server_id``. When the row already exists, updates
    name and icon only if they differ, via ``save(update_fields=...)``.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        server_id: Discord snowflake for the guild.
        server_name: Current guild name.
        icon_url: CDN URL for the guild icon; may be empty.

    Returns:
        ``(server, created)`` where ``created`` is ``True`` iff a new
        ``DiscordServer`` row was inserted on this call (Django ``get_or_create``
        semantics).

    Raises:
        None intentionally. Django ORM may raise database-related exceptions
        (e.g. ``IntegrityError``, ``OperationalError``) under concurrency or DB faults.

    Side effects:
        Reads/writes ``DiscordServer``. May emit ``logger.debug`` on update.
    """
    server, created = DiscordServer.objects.get_or_create(
        server_id=server_id,
        defaults={
            "server_name": server_name,
            "icon_url": icon_url,
        },
    )

    if not created:
        # Update fields if changed
        updated = False
        if server.server_name != server_name:
            server.server_name = server_name
            updated = True
        if server.icon_url != icon_url:
            server.icon_url = icon_url
            updated = True

        if updated:
            server.save(update_fields=["server_name", "icon_url", "updated_at"])
            logger.debug(f"Updated server: {server_name}")

    return server, created


def get_or_create_discord_channel(
    server: DiscordServer,
    channel_id: int,
    channel_name: str,
    channel_type: str,
    topic: str = "",
    position: int = 0,
    category_id: Optional[int] = None,
    category_name: str = "",
) -> Tuple[DiscordChannel, bool]:
    """Get or create a channel row and refresh fields when the row already exists.

    Uses ``get_or_create`` on ``channel_id``. Existing rows are updated when any
    of name, type, topic, position, or category fields change (``category_name`` is
    only applied when non-empty and different).

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        server: Parent ``DiscordServer`` (guild).
        channel_id: Discord snowflake for the channel.
        channel_name: Display name (e.g. without leading ``#``).
        channel_type: Exporter/discord type string (e.g. ``GuildTextChat``).
        topic: Channel topic text.
        position: Sort order within the guild.
        category_id: Parent category snowflake, or ``None`` if unknown/uncategorized.
        category_name: Human-readable category name when known.

    Returns:
        ``(channel, created)`` with Django ``get_or_create`` semantics for ``created``.

    Raises:
        None intentionally. Django ORM may raise database-related exceptions.

    Side effects:
        Reads/writes ``DiscordChannel``. May emit ``logger.debug`` on update.
    """
    channel, created = DiscordChannel.objects.get_or_create(
        channel_id=channel_id,
        defaults={
            "server": server,
            "channel_name": channel_name,
            "channel_type": channel_type,
            "topic": topic,
            "position": position,
            "category_id": category_id,
            "category_name": category_name,
        },
    )

    if not created:
        updated = False
        if channel.channel_name != channel_name:
            channel.channel_name = channel_name
            updated = True
        if channel.channel_type != channel_type:
            channel.channel_type = channel_type
            updated = True
        if channel.topic != topic:
            channel.topic = topic
            updated = True
        if channel.position != position:
            channel.position = position
            updated = True
        if category_id is not None and channel.category_id != category_id:
            channel.category_id = category_id
            updated = True
        if category_name and channel.category_name != category_name:
            channel.category_name = category_name
            updated = True

        if updated:
            channel.save(
                update_fields=[
                    "channel_name",
                    "channel_type",
                    "topic",
                    "position",
                    "category_id",
                    "category_name",
                    "updated_at",
                ]
            )
            logger.debug(f"Updated channel: {channel_name}")

    return channel, created


def create_or_update_discord_message(
    message_id: int,
    channel: DiscordChannel,
    author: DiscordProfile,
    content: str,
    message_created_at: datetime,
    message_edited_at: Optional[datetime] = None,
    reply_to_message_id: Optional[int] = None,
    attachment_urls: Optional[list] = None,
    message_type: str = "Default",
    is_pinned: bool = False,
) -> Tuple[DiscordMessage, bool]:
    """Create or update a single message by Discord ``message_id`` (upsert).

    Uses ``update_or_create`` so the row is keyed by ``message_id``; ``defaults``
    refresh channel, author, content, type, pins, timestamps, attachments, and
    clears ``is_deleted``. ``has_attachments`` is derived from ``attachment_urls``.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        message_id: Discord snowflake for the message.
        channel: Channel the message belongs to.
        author: ``DiscordProfile`` for the message author.
        content: Message body text.
        message_created_at: Original creation time (timezone-aware recommended).
        message_edited_at: Last edit time, if any.
        reply_to_message_id: Parent message snowflake for replies, or ``None``.
        attachment_urls: List of attachment URLs; ``None`` is treated as empty.
        message_type: Exporter/discord type string; empty coerces to the string ``Default``.
        is_pinned: Whether the message is pinned in the channel.

    Returns:
        ``(message, created)`` where ``created`` is ``True`` iff a new
        ``DiscordMessage`` row was inserted (Django ``update_or_create`` semantics).

    Raises:
        None intentionally. Django ORM may raise database-related exceptions.

    Side effects:
        Reads/writes ``DiscordMessage``.
    """
    if attachment_urls is None:
        attachment_urls = []

    message, created = DiscordMessage.objects.update_or_create(
        message_id=message_id,
        defaults={
            "channel": channel,
            "author": author,
            "content": content,
            "message_type": message_type or "Default",
            "is_pinned": is_pinned,
            "message_created_at": message_created_at,
            "message_edited_at": message_edited_at,
            "reply_to_message_id": reply_to_message_id,
            "has_attachments": len(attachment_urls) > 0,
            "attachment_urls": attachment_urls,
            "is_deleted": False,
        },
    )

    return message, created


def mark_message_deleted(
    message: DiscordMessage, deleted_at: Optional[datetime] = None
) -> DiscordMessage:
    """Soft-delete a message: set ``is_deleted`` and ``deleted_at``.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        message: Row to mark deleted (mutated in memory and saved).
        deleted_at: Deletion timestamp; defaults to ``django.utils.timezone.now()``.

    Returns:
        The same ``DiscordMessage`` instance after ``save(update_fields=...)``.

    Raises:
        None intentionally. Django ORM may raise database-related exceptions.

    Side effects:
        Updates ``DiscordMessage.is_deleted``, ``deleted_at``, ``updated_at``.
        Emits ``logger.debug``.
    """
    if deleted_at is None:
        deleted_at = django_timezone.now()

    message.is_deleted = True
    message.deleted_at = deleted_at
    message.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    logger.debug(f"Marked message {message.message_id} as deleted")
    return message


def add_or_update_reaction(
    message: DiscordMessage, emoji: str, count: int
) -> Tuple[DiscordReaction, bool]:
    """Upsert one reaction row per (message, emoji) with the given reaction count.

    Uses ``update_or_create`` on the unique pair ``(message, emoji)``.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        message: Message the reaction is on.
        emoji: Emoji string or custom emoji representation.
        count: Aggregated reaction count from the source payload.

    Returns:
        ``(reaction, created)`` with Django ``update_or_create`` semantics for ``created``.

    Raises:
        None intentionally. Django ORM may raise database-related exceptions.

    Side effects:
        Reads/writes ``DiscordReaction``.
    """
    reaction, created = DiscordReaction.objects.update_or_create(
        message=message, emoji=emoji, defaults={"count": count}
    )

    return reaction, created


def get_channel_latest_message_at(channel: DiscordChannel) -> Optional[datetime]:
    """Return the latest ``message_created_at`` among non-deleted messages in a channel.

    Read-only aggregate over ``DiscordMessage``; no writes.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        channel: Channel to scan.

    Returns:
        Maximum ``message_created_at`` for rows with ``is_deleted=False``, or
        ``None`` if there are no such messages.

    Raises:
        None intentionally. Django ORM may raise database-related exceptions.

    Side effects:
        None (read-only query).
    """
    row = DiscordMessage.objects.filter(channel=channel, is_deleted=False).aggregate(
        m=Max("message_created_at")
    )
    return row["m"]


def queryset_channels_with_recent_messages(
    server: DiscordServer,
    cutoff: datetime,
    channel_ids: Optional[List[int]] = None,
) -> QuerySet[DiscordChannel]:
    """Channels on ``server`` with at least one non-deleted message at or after ``cutoff``.

    Compares ``message_created_at`` to ``cutoff``; use timezone-aware datetimes for
    predictable UTC behavior. When ``channel_ids`` is set, restricts to those
    Discord ``channel_id`` values (snowflakes), not internal PKs.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        server: Guild whose channels are considered.
        cutoff: Inclusive lower bound on ``DiscordMessage.message_created_at``.
        channel_ids: Optional allowlist of Discord channel snowflakes.

    Returns:
        ``QuerySet`` of ``DiscordChannel`` ordered by ``position``, ``channel_name``.

    Raises:
        None intentionally. Django ORM may raise database-related exceptions.

    Side effects:
        None (read-only query).
    """
    pks = (
        DiscordMessage.objects.filter(
            channel__server=server,
            message_created_at__gte=cutoff,
            is_deleted=False,
        )
        .values_list("channel_id", flat=True)
        .distinct()
    )
    qs = DiscordChannel.objects.filter(server=server, pk__in=pks).order_by(
        "position", "channel_name"
    )
    if channel_ids:
        qs = qs.filter(channel_id__in=channel_ids)
    return qs


def get_active_channels(
    server: DiscordServer,
    days: int = 30,
    channel_ids: Optional[List[int]] = None,
) -> QuerySet[DiscordChannel]:
    """Same as ``queryset_channels_with_recent_messages`` with ``cutoff = now - days``.

    ``days`` is calendar-style span from ``django.utils.timezone.now()`` using
    ``datetime.timedelta``.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        server: Guild whose channels are considered.
        days: Lookback window in days from the current time.
        channel_ids: Optional allowlist of Discord channel snowflakes.

    Returns:
        ``QuerySet`` of ``DiscordChannel`` with recent activity.

    Raises:
        None intentionally. Django ORM may raise database-related exceptions.

    Side effects:
        None (read-only query; delegates to ``queryset_channels_with_recent_messages``).
    """
    from datetime import timedelta

    cutoff = django_timezone.now() - timedelta(days=days)
    return queryset_channels_with_recent_messages(server, cutoff, channel_ids)


# ---------------------------------------------------------------------------
# Bulk operations (for high-throughput message sync)
# ---------------------------------------------------------------------------


def bulk_upsert_discord_users(
    user_data_list: List[Union[DiscordLiveUserPayload, Dict[str, Any]]],
) -> Dict[int, DiscordProfile]:
    """Upsert author profiles for a batch of messages.

    Deduplicates by ``user_id`` (last dict wins). Existing ``DiscordProfile`` rows
    are fetched in one query and updated in Python when fields differ; missing
    users are created via ``get_or_create_discord_profile`` (no
    ``bulk_create(update_conflicts=True)`` because ``DiscordProfile`` uses MTI).

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        user_data_list: Dicts with at least ``user_id`` and ``username``; optional
            ``display_name``, ``avatar_url``, ``is_bot`` (see sync normalizers).

    Returns:
        Map ``discord_user_id -> DiscordProfile`` including database PKs on profiles.

    Raises:
        None intentionally. Invalid payloads raise
        :class:`~discord_activity_tracker.api_schemas.DiscordLiveSyncValidationError`.
        Django ORM may raise database-related exceptions.

    Side effects:
        Reads/writes ``cppa_user_tracker.DiscordProfile`` via queries and
        ``get_or_create_discord_profile``; may call ``profile.save()`` without
        ``update_fields`` when updating existing rows.
    """
    if not user_data_list:
        return {}

    from .api_schemas import parse_live_user

    normalized: list[DiscordLiveUserPayload] = []
    for d in user_data_list:
        if isinstance(d, dict):
            normalized.append(parse_live_user(d))
        else:
            normalized.append(d)

    # Deduplicate by user_id (last-seen wins)
    unique = {d.user_id: d for d in normalized}

    # Fetch existing profiles in one query
    existing = {
        p.discord_user_id: p
        for p in DiscordProfile.objects.filter(discord_user_id__in=list(unique.keys()))
    }

    result = {}
    for uid, d in unique.items():
        if uid in existing:
            profile = existing[uid]
            username_val = d.username or ""
            display_name_val = d.display_name or ""
            avatar_url_val = d.avatar_url or ""
            updated = False
            if username_val and profile.username != username_val:
                profile.username = username_val
                updated = True
            if display_name_val and profile.display_name != display_name_val:
                profile.display_name = display_name_val
                updated = True
            if avatar_url_val and profile.avatar_url != avatar_url_val:
                profile.avatar_url = avatar_url_val
                updated = True
            if profile.is_bot != d.is_bot:
                profile.is_bot = d.is_bot
                updated = True
            if updated:
                profile.save()
            result[uid] = profile
        else:
            profile, _ = get_or_create_discord_profile(
                discord_user_id=uid,
                username=d.username,
                display_name=d.display_name,
                avatar_url=d.avatar_url,
                is_bot=d.is_bot,
            )
            result[uid] = profile

    return result


def bulk_upsert_discord_messages(
    message_data_list: Sequence[Union[DiscordLivePreparedMessage, Dict[str, Any]]],
    channel: DiscordChannel,
    user_map: Dict[int, DiscordProfile],
) -> Dict[int, DiscordMessage]:
    """Bulk upsert messages for one channel using ``bulk_create(update_conflicts=True)``.

    Skips a message (with ``logger.warning``) when ``user_map`` has no profile for
    the author's ``user_id`` (``d["author"]["user_id"]``). Skips building rows when every message is skipped;
    then returns an empty dict.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        message_data_list: Normalized message dicts (``message_id``, ``author``, etc.).
        channel: Target channel for all rows.
        user_map: ``discord_user_id -> DiscordProfile`` from ``bulk_upsert_discord_users``.

    Returns:
        Map ``message_id -> DiscordMessage`` with PKs loaded (``id``, ``message_id`` only).

    Raises:
        None intentionally. Invalid payloads raise
        :class:`~discord_activity_tracker.api_schemas.DiscordLiveSyncValidationError`.
        Django ORM may raise database-related exceptions.

    Side effects:
        Writes ``DiscordMessage`` via ``bulk_create``. May emit ``logger.warning``.
    """
    if not message_data_list:
        return {}

    from .api_schemas import parse_live_message

    now = django_timezone.now()
    instances = []
    for raw in message_data_list:
        d = parse_live_message(raw) if isinstance(raw, dict) else raw
        author = user_map.get(d.author.user_id)
        if author is None:
            logger.warning("Skipping message %s: author not in user_map", d.message_id)
            continue
        attachments = d.attachment_urls or []
        instances.append(
            DiscordMessage(
                message_id=d.message_id,
                channel=channel,
                author=author,
                content=d.content or "",
                message_type=d.message_type or "Default",
                is_pinned=bool(d.is_pinned),
                message_created_at=d.message_created_at,
                message_edited_at=d.message_edited_at,
                reply_to_message_id=d.reply_to_message_id,
                has_attachments=len(attachments) > 0,
                attachment_urls=attachments,
                is_deleted=False,
                created_at=now,
                updated_at=now,
            )
        )

    if not instances:
        return {}

    DiscordMessage.objects.bulk_create(
        instances,
        update_conflicts=True,
        unique_fields=["message_id"],
        update_fields=[
            "channel",
            "author",
            "content",
            "message_type",
            "is_pinned",
            "message_created_at",
            "message_edited_at",
            "reply_to_message_id",
            "has_attachments",
            "attachment_urls",
            "is_deleted",
            "updated_at",
        ],
    )

    msg_ids = [inst.message_id for inst in instances]
    db_msgs = DiscordMessage.objects.filter(message_id__in=msg_ids).only(
        "id", "message_id"
    )
    return {m.message_id: m for m in db_msgs}


def bulk_upsert_discord_reactions(
    reaction_data_list: Sequence[Union[DiscordReactionPayload, Dict[str, Any]]],
    message_map: Dict[int, DiscordMessage],
) -> None:
    """Bulk upsert reactions using ``bulk_create(update_conflicts=True)``.

    Entries whose ``discord_message_id`` is missing from ``message_map`` are skipped
    silently (no log). Duplicate (message PK, emoji) pairs keep the **last** payload.

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        reaction_data_list: Dicts with ``discord_message_id``, ``emoji``, optional ``count``.
        message_map: ``message_id -> DiscordMessage`` from ``bulk_upsert_discord_messages``.

    Returns:
        None

    Raises:
        None intentionally. Invalid payloads raise
        :class:`~discord_activity_tracker.api_schemas.DiscordLiveSyncValidationError`.
        Django ORM may raise database-related exceptions.

    Side effects:
        Writes ``DiscordReaction``.
    """
    if not reaction_data_list:
        return

    now = django_timezone.now()
    # Deduplicate by (message_id, emoji) — keep last
    seen = {}
    for raw in reaction_data_list:
        d = parse_reaction(raw) if isinstance(raw, dict) else raw
        msg = message_map.get(d.discord_message_id)
        if msg is None:
            continue
        key = (msg.pk, d.emoji)
        seen[key] = DiscordReaction(
            message=msg,
            emoji=d.emoji,
            count=d.count if d.count is not None else 1,
            created_at=now,
            updated_at=now,
        )

    if not seen:
        return

    DiscordReaction.objects.bulk_create(
        list(seen.values()),
        update_conflicts=True,
        unique_fields=["message", "emoji"],
        update_fields=["count", "updated_at"],
    )


def bulk_process_message_batch(
    message_data_list: List[Union[DiscordLivePreparedMessage, Dict[str, Any]]],
    channel: DiscordChannel,
) -> int:
    """Run user upsert, message upsert, and reaction upsert inside one DB transaction.

    Return value is **always** ``len(message_data_list)`` when the input list is
    non-empty, even if some messages were skipped inside ``bulk_upsert_discord_messages``
    (skipped rows do not reduce the returned count).

    Does not perform Discord HTTP calls; does not emit ``CollectorFailureCategory``.

    Args:
        message_data_list: Batch of normalized message dicts for one channel.
        channel: Target ``DiscordChannel``.

    Returns:
        ``0`` if ``message_data_list`` is empty; otherwise ``len(message_data_list)``.

    Raises:
        None intentionally. Invalid payloads raise
        :class:`~discord_activity_tracker.api_schemas.DiscordLiveSyncValidationError`.
        Django ORM may raise database-related exceptions; on failure the whole transaction rolls back.

    Side effects:
        One ``transaction.atomic()`` block: writes profiles (via
        ``bulk_upsert_discord_users``), messages, and reactions. See those functions
        for logging and skip behavior.
    """
    if not message_data_list:
        return 0

    with transaction.atomic():
        # Phase 1: users
        from .api_schemas import parse_live_message

        prepared: list[DiscordLivePreparedMessage] = [
            parse_live_message(m) if isinstance(m, dict) else m
            for m in message_data_list
        ]
        user_data_by_id: dict[int, DiscordLiveUserPayload] = {}
        for msg in prepared:
            user_data_by_id[msg.author.user_id] = msg.author
        user_map = bulk_upsert_discord_users(list(user_data_by_id.values()))

        # Phase 2: messages
        message_map = bulk_upsert_discord_messages(prepared, channel, user_map)

        # Phase 3: reactions
        reaction_data: list[DiscordReactionPayload] = []
        for msg in prepared:
            for reaction in msg.reactions:
                if isinstance(reaction, dict):
                    emoji = reaction.get("emoji")
                    count = reaction.get("count", 0)
                else:
                    emoji = getattr(reaction, "emoji", None)
                    count = getattr(reaction, "count", 0)
                if emoji:
                    reaction_data.append(
                        parse_reaction(
                            {
                                "discord_message_id": msg.message_id,
                                "emoji": emoji,
                                "count": count,
                            }
                        )
                    )
        if reaction_data:
            bulk_upsert_discord_reactions(reaction_data, message_map)

    return len(message_data_list)
