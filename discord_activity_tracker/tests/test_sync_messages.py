"""Tests for discord_activity_tracker.sync.messages."""

import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone as django_timezone

from cppa_user_tracker.services import get_or_create_discord_profile
from discord_activity_tracker.models import DiscordChannel, DiscordServer
from discord_activity_tracker.services import (
    add_or_update_reaction,
    bulk_process_message_batch,
    create_or_update_discord_message,
)
from asgiref.sync import sync_to_async as asgiref_sync_to_async

from discord_activity_tracker.services import (
    get_or_create_discord_channel,
    get_or_create_discord_server,
)
from discord_activity_tracker.sync import messages as messages_mod
from discord_activity_tracker.sync.messages import (
    _prepare_message_data,
    _process_message_data,
    _process_messages_in_batches,
    sync_all_channels,
    sync_channel_messages,
    sync_channel_messages_async,
    sync_channels,
    sync_channels_async,
    sync_guild,
    sync_guild_async,
)


def _uniq_id() -> int:
    """Discord-sized positive int; avoids collisions when sync_to_async sees committed rows."""
    return uuid.uuid4().int % (2**50)


def _sample_api_message(mid=100, uid=7, ts=None):
    if ts is None:
        ts = "2026-03-01T12:00:00+00:00"
    return {
        "id": mid,
        "content": "hello",
        "author": {
            "id": uid,
            "username": "alice",
            "display_name": "Alice",
            "avatar_url": "",
            "bot": False,
        },
        "created_at": ts,
        "edited_at": None,
        "reference": {"message_id": None},
        "attachments": [],
        "reactions": [{"emoji": "👍", "count": 1}],
    }


@pytest.mark.django_db
def test_sync_guild_async_creates_server():
    gid = _uniq_id()

    async def main():
        client = MagicMock()
        guild = MagicMock()
        guild.id = gid
        guild.name = "Guild"
        guild.icon = None
        client.get_guild = AsyncMock(return_value=guild)
        with _selective_sync_to_async_guild():
            return await sync_guild_async(client, gid)

    server = asyncio.run(main())
    assert server.server_id == gid
    assert server.server_name == "Guild"


@pytest.mark.django_db
def test_sync_guild_async_existing_server():
    gid = _uniq_id()

    async def main():
        client = MagicMock()
        guild = MagicMock()
        guild.id = gid
        guild.name = "Guild"
        guild.icon = None
        client.get_guild = AsyncMock(return_value=guild)

        def router(fn):
            if fn is get_or_create_discord_server:

                async def fake_get_or_create(**kwargs):
                    m = MagicMock()
                    m.server_id = kwargs["server_id"]
                    m.server_name = kwargs["server_name"]
                    return m, False

                return fake_get_or_create

            return asgiref_sync_to_async(fn, thread_sensitive=True)

        with patch(
            "discord_activity_tracker.sync.messages.sync_to_async",
            side_effect=router,
        ):
            return await sync_guild_async(client, gid)

    server = asyncio.run(main())
    assert server.server_id == gid


@pytest.mark.django_db
def test_sync_guild_async_missing_guild_raises():
    async def main():
        client = MagicMock()
        client.get_guild = AsyncMock(return_value=None)
        await sync_guild_async(client, 999)

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(main())


def _selective_sync_to_async_guild():
    """Stub server persistence so guild sync tests do not insert DiscordServer rows."""

    def router(fn):
        if fn is get_or_create_discord_server:

            async def fake_get_or_create(**kwargs):
                m = MagicMock()
                m.server_id = kwargs["server_id"]
                m.server_name = kwargs["server_name"]
                return m, True

            return fake_get_or_create

        return asgiref_sync_to_async(fn, thread_sensitive=True)

    return patch(
        "discord_activity_tracker.sync.messages.sync_to_async",
        side_effect=router,
    )


def _selective_sync_to_async_channels():
    """Avoid ORM from thread pool (pytest-django tx); only stub channel creation."""

    def router(fn):
        if fn is get_or_create_discord_channel:

            async def fake_get_or_create(**kwargs):
                m = MagicMock()
                m.channel_id = kwargs["channel_id"]
                m.channel_name = kwargs["channel_name"]
                return m, True

            return fake_get_or_create

        return asgiref_sync_to_async(fn, thread_sensitive=True)

    return patch(
        "discord_activity_tracker.sync.messages.sync_to_async",
        side_effect=router,
    )


@pytest.mark.django_db
def test_sync_channels_async_creates_channels():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")

    async def main():
        client = MagicMock()
        ch = MagicMock()
        ch.id = cid
        ch.name = "general"
        ch.type = MagicMock()
        ch.type.__str__ = lambda *_: "text"
        ch.topic = "t"
        ch.position = 1
        client.get_channels = AsyncMock(return_value=[ch])

        with _selective_sync_to_async_channels():
            return await sync_channels_async(client, server, gid)

    channels = asyncio.run(main())
    assert len(channels) == 1
    assert channels[0].channel_id == cid


def test_prepare_message_data_requires_created_at():
    assert _prepare_message_data({"id": 1, "author": {}}) is None


def test_prepare_message_data_ok():
    raw = _sample_api_message()
    out = _prepare_message_data(raw)
    assert out is not None
    assert out["message_id"] == 100
    assert out["author"]["user_id"] == 7


@pytest.mark.django_db
def test_process_messages_in_batches_skips_empty_prepared():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )

    async def main():
        return await _process_messages_in_batches(
            channel, [{"id": 1, "author": {}}], batch_size=10
        )

    assert asyncio.run(main()) == 0


def _selective_sync_to_async_bulk_batch():
    """Avoid ORM from sync_to_async worker threads (FK visibility across connections)."""

    def router(fn):
        if fn is bulk_process_message_batch:

            async def fake_bulk(batch, _channel):
                return len(batch)

            return fake_bulk

        return asgiref_sync_to_async(fn, thread_sensitive=True)

    return patch(
        "discord_activity_tracker.sync.messages.sync_to_async",
        side_effect=router,
    )


@pytest.mark.django_db
def test_process_messages_in_batches_runs_bulk_for_valid_messages():
    gid = _uniq_id()
    cid = _uniq_id()
    mid = _uniq_id()
    uid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )

    async def main():
        with _selective_sync_to_async_bulk_batch():
            return await _process_messages_in_batches(
                channel, [_sample_api_message(mid=mid, uid=uid)], batch_size=500
            )

    assert asyncio.run(main()) == 1


@pytest.mark.django_db
def test_process_message_data_skips_without_created_at():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )

    def router(fn):
        if fn is get_or_create_discord_profile:

            async def fake_profile(**_kwargs):
                return MagicMock(), True

            return fake_profile

        return asgiref_sync_to_async(fn, thread_sensitive=True)

    async def main():
        with patch(
            "discord_activity_tracker.sync.messages.sync_to_async",
            side_effect=router,
        ):
            await _process_message_data(
                channel,
                {"id": _uniq_id(), "author": {}, "created_at": None},
            )

    asyncio.run(main())


def _selective_sync_to_async_process_message_ok():
    def router(fn):
        if fn is get_or_create_discord_profile:

            async def fake_profile(**_kwargs):
                return MagicMock(), True

            return fake_profile
        if fn is create_or_update_discord_message:

            async def fake_msg(**kwargs):
                m = MagicMock()
                m.message_id = kwargs["message_id"]
                m.channel_name = kwargs["channel"].channel_name
                return m, True

            return fake_msg
        if fn is add_or_update_reaction:

            async def fake_reaction(*_a, **_kw):
                return MagicMock(), True

            return fake_reaction

        return asgiref_sync_to_async(fn, thread_sensitive=True)

    return patch(
        "discord_activity_tracker.sync.messages.sync_to_async",
        side_effect=router,
    )


@pytest.mark.django_db
def test_process_message_data_creates_message():
    gid = _uniq_id()
    cid = _uniq_id()
    mid = _uniq_id()
    uid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )

    async def main():
        with _selective_sync_to_async_process_message_ok():
            await _process_message_data(channel, _sample_api_message(mid=mid, uid=uid))

    asyncio.run(main())


@pytest.mark.django_db
def test_process_message_data_swallows_inner_errors():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )

    async def main():
        with patch.object(
            messages_mod,
            "parse_discord_user",
            side_effect=RuntimeError("bad author"),
        ):
            await _process_message_data(
                channel, _sample_api_message(mid=_uniq_id(), uid=_uniq_id())
            )

    asyncio.run(main())


def _sync_to_async_updates_only():
    def router(fn):
        if fn.__name__ == "update_channel_last_synced":

            async def inner(ch):
                ch.last_synced_at = django_timezone.now()
                return ch

            return inner
        if fn.__name__ == "update_channel_last_activity":

            async def inner(_ch, _ts):
                return None

            return inner

        return asgiref_sync_to_async(fn, thread_sensitive=True)

    return patch(
        "discord_activity_tracker.sync.messages.sync_to_async",
        side_effect=router,
    )


@pytest.mark.django_db
def test_sync_channel_messages_async_full_sync():
    gid = _uniq_id()
    cid = _uniq_id()
    author_uid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="general",
        channel_type="text",
    )

    async def main():
        client = MagicMock()
        dch = MagicMock()
        dch.name = "general"
        client.get_channel = AsyncMock(return_value=dch)

        msg = _sample_api_message(mid=_uniq_id(), uid=author_uid)
        client.fetch_messages_since = AsyncMock(return_value=[msg])

        with patch.object(
            messages_mod,
            "_process_messages_in_batches",
            new_callable=AsyncMock,
            return_value=1,
        ), _sync_to_async_updates_only():
            await sync_channel_messages_async(client, channel, gid, full_sync=True)

    asyncio.run(main())

    assert channel.last_synced_at is not None


@pytest.mark.django_db
def test_sync_channel_messages_async_no_discord_channel():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="general",
        channel_type="text",
    )

    async def main():
        client = MagicMock()
        client.get_channel = AsyncMock(return_value=None)
        await sync_channel_messages_async(client, channel, gid)

    asyncio.run(main())

    channel.refresh_from_db()
    assert channel.last_synced_at is None


@pytest.mark.django_db
def test_sync_channel_messages_async_raises():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="general",
        channel_type="text",
    )

    async def main():
        client = MagicMock()
        client.get_channel = AsyncMock(side_effect=RuntimeError("boom"))
        await sync_channel_messages_async(client, channel, gid)

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(main())


@pytest.mark.django_db
def test_sync_guild_wrapper_runs_and_closes():
    async def fake_guild(_client, _gid):
        return MagicMock()

    with patch(
        "discord_activity_tracker.sync.messages.DiscordSyncClient"
    ) as Cls, patch(
        "discord_activity_tracker.sync.messages.sync_guild_async",
        new=fake_guild,
    ):
        inst = Cls.return_value
        inst.close = AsyncMock()

        def client_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        inst.run = MagicMock(side_effect=client_run)
        inst.shutdown_sync = MagicMock()
        sync_guild("token", 1)

    assert inst.run.call_count == 1
    inst.shutdown_sync.assert_called_once()


@pytest.mark.django_db
def test_sync_channels_wrapper():
    gid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")

    async def fake_channels(_c, _s, _g):
        return []

    with patch(
        "discord_activity_tracker.sync.messages.DiscordSyncClient"
    ) as Cls, patch(
        "discord_activity_tracker.sync.messages.sync_channels_async",
        new=fake_channels,
    ):
        inst = Cls.return_value
        inst.close = AsyncMock()

        def client_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        inst.run = MagicMock(side_effect=client_run)
        inst.shutdown_sync = MagicMock()
        sync_channels("token", server, gid)

    assert inst.run.call_count == 1
    inst.shutdown_sync.assert_called_once()


@pytest.mark.django_db
def test_sync_channel_messages_wrapper():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )

    async def fake_sync(*_args, **_kwargs):
        return None

    with patch(
        "discord_activity_tracker.sync.messages.DiscordSyncClient"
    ) as Cls, patch(
        "discord_activity_tracker.sync.messages.sync_channel_messages_async",
        new=fake_sync,
    ):
        inst = Cls.return_value
        inst.close = AsyncMock()

        def client_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        inst.run = MagicMock(side_effect=client_run)
        inst.shutdown_sync = MagicMock()
        sync_channel_messages("token", channel, gid, full_sync=True)

    assert inst.run.call_count == 1
    inst.shutdown_sync.assert_called_once()


@pytest.mark.django_db
def test_sync_all_channels_respects_active_filter():
    now = django_timezone.now()
    gid = _uniq_id()
    cid_active = _uniq_id()
    cid_stale = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    active_ch = DiscordChannel.objects.create(
        server=server,
        channel_id=cid_active,
        channel_name="active",
        channel_type="text",
        last_activity_at=now,
    )
    DiscordChannel.objects.create(
        server=server,
        channel_id=cid_stale,
        channel_name="stale",
        channel_type="text",
        last_activity_at=now - timedelta(days=90),
    )

    channels_snapshot = list(DiscordChannel.objects.filter(server=server))

    async def guild_ok(_c, _gid):
        return server

    async def channels_ok(_c, _srv, _gid):
        return channels_snapshot

    sync_body = AsyncMock()

    with patch(
        "discord_activity_tracker.sync.messages.DiscordSyncClient"
    ) as Cls, patch(
        "discord_activity_tracker.sync.messages.sync_guild_async",
        new=guild_ok,
    ), patch(
        "discord_activity_tracker.sync.messages.sync_channels_async",
        new=channels_ok,
    ), patch(
        "discord_activity_tracker.sync.messages._sync_all_channels_async",
        new=sync_body,
    ):
        inst = Cls.return_value
        inst.close = AsyncMock()

        def client_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        inst.run = MagicMock(side_effect=client_run)
        inst.shutdown_sync = MagicMock()
        sync_all_channels("tok", gid, active_only=True, active_days=30, full_sync=False)

    assert inst.run.call_count == 3
    inst.shutdown_sync.assert_called_once()
    sync_body.assert_awaited_once()
    args, _kwargs = sync_body.call_args
    passed_channels = args[1]
    assert len(passed_channels) == 1
    assert passed_channels[0].pk == active_ch.pk


@pytest.mark.django_db
def test_sync_all_channels_full_sync_no_active_filter():
    gid = _uniq_id()
    cid = _uniq_id()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
        last_activity_at=None,
    )

    channels_snapshot = list(DiscordChannel.objects.filter(server=server))

    async def guild_ok(_c, _gid):
        return server

    async def channels_ok(_c, _srv, _gid):
        return channels_snapshot

    sync_body = AsyncMock()

    with patch(
        "discord_activity_tracker.sync.messages.DiscordSyncClient"
    ) as Cls, patch(
        "discord_activity_tracker.sync.messages.sync_guild_async",
        new=guild_ok,
    ), patch(
        "discord_activity_tracker.sync.messages.sync_channels_async",
        new=channels_ok,
    ), patch(
        "discord_activity_tracker.sync.messages._sync_all_channels_async",
        new=sync_body,
    ):
        inst = Cls.return_value
        inst.close = AsyncMock()

        def client_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        inst.run = MagicMock(side_effect=client_run)
        inst.shutdown_sync = MagicMock()
        sync_all_channels("tok", gid, full_sync=True)

    assert inst.run.call_count == 3
    inst.shutdown_sync.assert_called_once()
    sync_body.assert_awaited_once()
    args, _kwargs = sync_body.call_args
    assert len(args[1]) == 1
