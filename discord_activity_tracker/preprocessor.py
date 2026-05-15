"""Pinecone preprocess function for discord_activity_tracker.

Follows the contract defined in docs/Pinecone_preprocess_guideline.md and
mirrors the structure of cppa_slack_tracker.preprocessor.

Groups DiscordMessage rows by channel, merges reply chains (thread roots with
their direct replies) into single documents (one line per message:
``author: "text"``, joined by newlines), filters short / empty content, and
emits ``{"content": str, "metadata": dict}`` records for cppa_pinecone_sync.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from django.conf import settings
from django.db.models import Q

from core.utils.text_processing import clean_discord_text
from discord_activity_tracker.models import DiscordChannel, DiscordMessage

logger = logging.getLogger(__name__)

# Minimum characters a document's plain-text content must have before it is
# sent to Pinecone.  Mirrors PINECONE_MIN_TEXT_LENGTH in other preprocessors.
_DEFAULT_MIN_TEXT_LENGTH = 20


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _min_text_length() -> int:
    return int(getattr(settings, "PINECONE_MIN_TEXT_LENGTH", _DEFAULT_MIN_TEXT_LENGTH))


def _is_content_too_short(text: str) -> bool:
    return len(text.strip()) < _min_text_length()


# ---------------------------------------------------------------------------
# ID normalisation
# ---------------------------------------------------------------------------


def _normalize_failed_ids(failed_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in failed_ids or []:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------


def _build_reply_chains(
    messages: list[DiscordMessage],
) -> list[list[DiscordMessage]]:
    """Group messages into reply chains.

    For each root message (not a reply to another message in this batch), the
    chain is the root plus every other message in the batch whose
    ``reply_to_message_id`` equals the root's ``message_id`` (direct replies
    only). Standalone messages become single-item chains. Nested replies
    (reply-to-reply) whose parent is not the root are emitted as separate
    single-message chains by the orphan pass.

    Long merged ``content`` is split later by ``cppa_pinecone_sync`` ingestion
    when ``is_chunked=False`` (see docs/Pinecone_preprocess_guideline.md).
    """
    by_id: dict[int, DiscordMessage] = {m.message_id: m for m in messages}
    assigned: set[int] = set()
    chains: list[list[DiscordMessage]] = []

    for msg in messages:
        if msg.message_id in assigned:
            continue
        if msg.reply_to_message_id and msg.reply_to_message_id in by_id:
            continue  # Will be picked up as part of a root's chain
        # This message is a root (or has no local parent)
        chain = [msg]
        assigned.add(msg.message_id)
        for reply in messages:
            if reply.message_id in assigned:
                continue
            if reply.reply_to_message_id == msg.message_id:
                chain.append(reply)
                assigned.add(reply.message_id)
        chains.append(chain)

    # Any remaining (orphan replies whose root wasn't in this batch)
    for msg in messages:
        if msg.message_id not in assigned:
            chains.append([msg])

    return chains


def _pinecone_channel_display_name(channel: DiscordChannel) -> str:
    """Human-readable channel label for Pinecone: ``category - channel`` when category exists."""
    name = (channel.channel_name or "").strip()
    cat = (channel.category_name or "").strip()
    if cat:
        return f"{cat} - {name}" if name else cat
    return name or "?"


def _format_chain_message_line(msg: DiscordMessage, cleaned: str) -> str:
    """One line for merged reply-chain content: ``username: "message text"``."""
    username = msg.author.username if getattr(msg, "author_id", None) else "unknown"
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'{username}: "{escaped}"'


def _chain_to_document(
    chain: list[DiscordMessage],
) -> Optional[dict[str, Any]]:
    """Convert a reply chain to a Pinecone document dict, or None if filtered."""
    parts: list[str] = []
    ids: list[str] = []

    for msg in chain:
        raw = (msg.content or "").strip()
        if not raw:
            continue
        cleaned = clean_discord_text(raw)
        if not cleaned:
            continue
        parts.append(_format_chain_message_line(msg, cleaned))
        ids.append(str(msg.message_id))

    if not parts:
        return None

    content = "\n".join(parts)
    if _is_content_too_short(content):
        return None

    root = chain[0]
    channel = root.channel
    server = channel.server

    try:
        ts = int(root.message_created_at.astimezone(timezone.utc).timestamp())
    except (AttributeError, OSError, OverflowError):
        ts = 0

    return {
        "content": content,
        "metadata": {
            "doc_id": str(root.message_id),
            "type": "discord",
            "channel_id": str(channel.channel_id),
            "channel_name": _pinecone_channel_display_name(channel),
            "server_id": str(server.server_id),
            "server_name": server.server_name,
            "author": (
                root.author.username if getattr(root, "author_id", None) else "unknown"
            ),
            "timestamp": ts,
            "is_reply_chain": len(chain) > 1,
            "source_ids": ",".join(ids),
        },
    }


# ---------------------------------------------------------------------------
# Public preprocess function
# ---------------------------------------------------------------------------


def preprocess_discord_for_pinecone(
    failed_ids: list[str],
    final_sync_at: datetime | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Build Pinecone sync documents for Discord messages.

    Args:
        failed_ids: Source IDs (message snowflakes as strings) that failed in a
            previous sync run and should be retried.
        final_sync_at: Timestamp of the last successful sync; ``None`` for first sync.

    Returns:
        ``(documents, is_chunked)`` where ``documents`` is a list of
        ``{"content": str, "metadata": dict}`` records and ``is_chunked``
        is ``False`` (whole documents; the ingestion pipeline may chunk them).
    """
    normalized_failed = _normalize_failed_ids(failed_ids)

    qs = (
        DiscordMessage.objects.select_related("channel__server", "author")
        .filter(is_deleted=False)
        .order_by("message_created_at")
    )

    messages_new: list[DiscordMessage] = []
    messages_failed: list[DiscordMessage] = []

    if final_sync_at is None and not normalized_failed:
        # First sync — index everything
        messages_new = list(qs)
        logger.info(
            "preprocess_discord: first sync, loaded %d messages", len(messages_new)
        )
    else:
        if final_sync_at is not None:
            messages_new = list(qs.filter(updated_at__gt=final_sync_at))
            logger.info(
                "preprocess_discord: incremental, loaded %d new messages",
                len(messages_new),
            )
        if normalized_failed:
            messages_failed = list(
                qs.filter(
                    Q(
                        message_id__in=[
                            int(fid) for fid in normalized_failed if fid.isdigit()
                        ]
                    )
                )
            )
            logger.info(
                "preprocess_discord: retrying %d failed messages", len(messages_failed)
            )

    all_messages = messages_new + messages_failed
    if not all_messages:
        logger.info("preprocess_discord: nothing to sync")
        return [], False

    chains = _build_reply_chains(all_messages)

    docs: list[dict[str, Any]] = []
    seen_doc_ids: set[str] = set()

    for chain in chains:
        doc = _chain_to_document(chain)
        if doc is None:
            continue
        doc_id = doc["metadata"]["doc_id"]
        if doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(doc_id)
        docs.append(doc)

    logger.info("preprocess_discord: built %d Pinecone documents", len(docs))
    return docs, False
