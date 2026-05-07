"""Unit tests for discord_activity_tracker.preprocessor."""

from datetime import datetime, timezone

import pytest

from core.utils.text_processing import clean_discord_text
from cppa_user_tracker.models import DiscordProfile
from discord_activity_tracker.models import (
    DiscordChannel,
    DiscordMessage,
    DiscordServer,
)
from discord_activity_tracker.preprocessor import (
    _build_reply_chains,
    _chain_to_document,
    _is_content_too_short,
    _normalize_failed_ids,
    _pinecone_channel_display_name,
    preprocess_discord_for_pinecone,
)

# Content that passes PINECONE_MIN_TEXT_LENGTH=50 (default in settings.py)
_L = "This is a sample Discord message with enough text for Pinecone indexing purposes."
_L2 = "Another Discord message long enough to pass the Pinecone minimum text length filter."
_L_REPLY = (
    "This is a reply message also long enough to pass the Pinecone minimum text length."
)
_L_RETRY = (
    "This failed message is long enough to be retried by the Pinecone sync pipeline."
)
_L_META = "This message has enough characters to pass the minimum text length check in Pinecone."


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def test_clean_discord_text_removes_user_mentions():
    assert clean_discord_text("discussion <@123456>") == "discussion"


def test_clean_discord_text_removes_role_mentions():
    assert "<@&" not in clean_discord_text("readership <@&9876>")
    assert clean_discord_text("readership <@&9876>") == "readership"


def test_clean_discord_text_removes_channel_refs():
    assert "<#" not in clean_discord_text("see <#5555>")
    assert clean_discord_text("see <#5555>") == "see"


def test_clean_discord_text_converts_custom_emoji():
    assert ":wave:" in clean_discord_text("<:wave:123456789>")


def test_clean_discord_text_preserves_plain_text():
    assert clean_discord_text("alpha beta gamma") == "alpha beta gamma"


def test_clean_discord_text_removes_greeting_after_mention():
    assert clean_discord_text("hi <@1>") == ""


def test_clean_discord_text_removes_thanks_keeps_substance():
    assert clean_discord_text("thanks <@9> everyone here") == "everyone here"


def test_is_content_too_short_below_threshold():
    assert _is_content_too_short("hi") is True


def test_is_content_too_short_at_or_above_threshold():
    assert _is_content_too_short(_L) is False


def test_normalize_failed_ids_deduplicates():
    result = _normalize_failed_ids(["1", "2", "1", "3"])
    assert result.count("1") == 1
    assert len(result) == 3


def test_normalize_failed_ids_strips_whitespace():
    result = _normalize_failed_ids([" 1 ", "2"])
    assert "1" in result


def test_normalize_failed_ids_skips_empty():
    result = _normalize_failed_ids(["", None, "5"])  # type: ignore[list-item]
    assert "" not in result
    assert "5" in result


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server(db):
    import uuid

    return DiscordServer.objects.create(
        server_id=uuid.uuid4().int % (2**50),
        server_name="TestGuild",
        icon_url="",
    )


@pytest.fixture
def channel(server):
    import uuid

    return DiscordChannel.objects.create(
        server=server,
        channel_id=uuid.uuid4().int % (2**50),
        channel_name="general",
        channel_type="GuildTextChat",
    )


@pytest.fixture
def author(db):
    import uuid

    return DiscordProfile.objects.create(
        discord_user_id=uuid.uuid4().int % (2**50),
        username="alice",
        display_name="Alice",
        avatar_url="",
        is_bot=False,
    )


@pytest.mark.django_db
def test_pinecone_channel_display_name_with_category(server):
    import uuid

    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=uuid.uuid4().int % (2**50),
        channel_name="cpp-discussion",
        channel_type="GuildTextChat",
        category_name="Together",
    )
    assert _pinecone_channel_display_name(ch) == "Together - cpp-discussion"


@pytest.mark.django_db
def test_pinecone_channel_display_name_without_category(channel):
    assert _pinecone_channel_display_name(channel) == "general"


@pytest.mark.django_db
def test_pinecone_channel_display_name_whitespace_category(server):
    import uuid

    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=uuid.uuid4().int % (2**50),
        channel_name="x",
        channel_type="GuildTextChat",
        category_name="   ",
    )
    assert _pinecone_channel_display_name(ch) == "x"


def _make_msg(channel, author, message_id, content, ts=None, reply_to=None):
    if ts is None:
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return DiscordMessage.objects.create(
        message_id=message_id,
        channel=channel,
        author=author,
        content=content,
        message_created_at=ts,
        reply_to_message_id=reply_to,
    )


# ---------------------------------------------------------------------------
# _build_reply_chains
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_build_reply_chains_standalone_messages(channel, author):
    m1 = _make_msg(channel, author, 1001, _L)
    m2 = _make_msg(channel, author, 1002, _L2)
    chains = _build_reply_chains([m1, m2])
    assert len(chains) == 2
    assert all(len(c) == 1 for c in chains)


@pytest.mark.django_db
def test_build_reply_chains_groups_replies(channel, author):
    root = _make_msg(channel, author, 2001, _L)
    reply1 = _make_msg(channel, author, 2002, _L_REPLY, reply_to=2001)
    reply2 = _make_msg(channel, author, 2003, _L2, reply_to=2001)
    chains = _build_reply_chains([root, reply1, reply2])
    assert len(chains) == 1
    chain = chains[0]
    assert chain[0].message_id == root.message_id
    assert len(chain) == 3


@pytest.mark.django_db
def test_build_reply_chains_orphan_reply(channel, author):
    """Reply whose root is not in the batch becomes its own single-item chain."""
    orphan = _make_msg(channel, author, 3001, _L, reply_to=9999)
    chains = _build_reply_chains([orphan])
    assert len(chains) == 1
    assert chains[0][0].message_id == orphan.message_id


# ---------------------------------------------------------------------------
# _chain_to_document
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chain_to_document_single_message(channel, author):
    msg = _make_msg(channel, author, 4001, _L)
    doc = _chain_to_document([msg])
    assert doc is not None
    assert _L.lower() in doc["content"]
    assert doc["content"].startswith('alice: "')
    assert doc["content"].endswith('"')
    meta = doc["metadata"]
    assert meta["doc_id"] == str(msg.message_id)
    assert meta["type"] == "discord"
    assert meta["channel_name"] == channel.channel_name
    assert meta["server_name"] == channel.server.server_name
    assert meta["is_reply_chain"] is False
    assert meta["source_ids"] == str(msg.message_id)


@pytest.mark.django_db
def test_chain_to_document_escapes_internal_double_quotes(channel, author):
    body = 'Before "quoted" after and more text so we exceed fifty chars easily fine.'
    assert len(body) >= 50
    msg = _make_msg(channel, author, 4004, body)
    doc = _chain_to_document([msg])
    assert doc is not None
    assert '\\"quoted\\"' in doc["content"]


@pytest.mark.django_db
def test_chain_to_document_reply_chain(channel, author):
    root = _make_msg(channel, author, 5001, _L)
    reply = _make_msg(channel, author, 5002, _L_REPLY)
    doc = _chain_to_document([root, reply])
    assert doc is not None
    assert doc["metadata"]["is_reply_chain"] is True
    assert str(root.message_id) in doc["metadata"]["source_ids"]
    assert str(reply.message_id) in doc["metadata"]["source_ids"]
    assert "\n" in doc["content"]
    assert _L.lower() in doc["content"] and _L_REPLY.lower() in doc["content"]
    assert doc["content"].startswith("alice:")


@pytest.mark.django_db
def test_chain_to_document_empty_content_returns_none(channel, author):
    msg = _make_msg(channel, author, 6001, "")
    doc = _chain_to_document([msg])
    assert doc is None


@pytest.mark.django_db
def test_chain_to_document_too_short_returns_none(channel, author):
    msg = _make_msg(channel, author, 6002, "hi")
    doc = _chain_to_document([msg])
    assert doc is None


# ---------------------------------------------------------------------------
# preprocess_discord_for_pinecone integration tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_sync_indexes_all_messages(channel, author):
    _make_msg(channel, author, 7001, _L)
    _make_msg(channel, author, 7002, _L2)
    docs, is_chunked = preprocess_discord_for_pinecone(
        failed_ids=[], final_sync_at=None
    )
    assert is_chunked is False
    doc_ids = {d["metadata"]["doc_id"] for d in docs}
    assert "7001" in doc_ids
    assert "7002" in doc_ids


@pytest.mark.django_db
def test_incremental_sync_only_new_messages(channel, author):
    old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)

    _make_msg(channel, author, 8001, _L, ts=old_ts)
    _make_msg(channel, author, 8002, _L2, ts=new_ts)

    # Force updated_at on old message to be before cutoff
    DiscordMessage.objects.filter(message_id=8001).update(updated_at=old_ts)

    cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
    docs, _ = preprocess_discord_for_pinecone(failed_ids=[], final_sync_at=cutoff)
    doc_ids = {d["metadata"]["doc_id"] for d in docs}
    # 8001 updated_at was forced to old_ts, before cutoff → not included
    assert "8001" not in doc_ids


@pytest.mark.django_db
def test_failed_ids_are_retried(channel, author):
    _make_msg(channel, author, 9001, _L_RETRY)
    # Simulate that a sync already ran (cutoff in future = no new messages)
    cutoff = datetime(2099, 1, 1, tzinfo=timezone.utc)
    docs, _ = preprocess_discord_for_pinecone(failed_ids=["9001"], final_sync_at=cutoff)
    doc_ids = {d["metadata"]["doc_id"] for d in docs}
    assert "9001" in doc_ids


@pytest.mark.django_db
def test_empty_db_returns_empty_list():
    DiscordMessage.objects.all().delete()
    docs, _ = preprocess_discord_for_pinecone(failed_ids=[], final_sync_at=None)
    assert docs == []


@pytest.mark.django_db
def test_metadata_shape(channel, author):
    _make_msg(channel, author, 10001, _L_META)
    docs, _ = preprocess_discord_for_pinecone(failed_ids=[], final_sync_at=None)
    doc = next((d for d in docs if d["metadata"]["doc_id"] == "10001"), None)
    assert doc is not None
    meta = doc["metadata"]
    required_keys = {
        "doc_id",
        "type",
        "channel_id",
        "channel_name",
        "server_id",
        "server_name",
        "author",
        "timestamp",
        "is_reply_chain",
        "source_ids",
    }
    assert required_keys.issubset(meta.keys())
    assert meta["type"] == "discord"
    assert meta["author"] == "alice"
    assert meta["channel_id"] == str(channel.channel_id)
    assert meta["server_id"] == str(channel.server.server_id)
    assert meta["server_name"] == channel.server.server_name
    assert isinstance(meta["timestamp"], int)


@pytest.mark.django_db
def test_metadata_channel_name_includes_category(server, author):
    import uuid

    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=uuid.uuid4().int % (2**50),
        channel_name="cpp-discussion",
        channel_type="GuildTextChat",
        category_name="C & C++ Together",
    )
    _make_msg(ch, author, 10002, _L_META)
    docs, _ = preprocess_discord_for_pinecone(failed_ids=[], final_sync_at=None)
    doc = next((d for d in docs if d["metadata"]["doc_id"] == "10002"), None)
    assert doc is not None
    assert doc["metadata"]["channel_name"] == "C & C++ Together - cpp-discussion"
    assert doc["metadata"]["server_name"] == server.server_name
