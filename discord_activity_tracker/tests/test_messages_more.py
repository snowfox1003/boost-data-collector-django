"""Extra coverage for discord_activity_tracker.sync.messages branches."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone as django_timezone

from discord_activity_tracker.models import DiscordChannel, DiscordServer
from discord_activity_tracker.sync import messages as messages_mod
from discord_activity_tracker.sync.messages import (
    _sync_all_channels_async,
    sync_channel_messages_async,
)


def _uniq():
    import uuid

    return uuid.uuid4().int % (2**50)


@pytest.mark.django_db
def test_sync_all_channels_async_continues_on_channel_failure():
    async def boom(*_a, **_kw):
        raise RuntimeError("sync failed")

    server = DiscordServer.objects.create(
        server_id=_uniq(), server_name="S", icon_url=""
    )
    ch = DiscordChannel.objects.create(
        server=server,
        channel_id=_uniq(),
        channel_name="x",
        channel_type="text",
    )

    async def main():
        client = MagicMock()
        with patch(
            "discord_activity_tracker.sync.messages.sync_channel_messages_async",
            new=boom,
        ):
            await _sync_all_channels_async(client, [ch], server.server_id)

    asyncio.run(main())


@pytest.mark.django_db
def test_sync_channel_messages_async_since_date_branch():
    gid = _uniq()
    cid = _uniq()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )
    since = django_timezone.now() - timedelta(days=1)

    async def main():
        client = MagicMock()
        client.get_channel = AsyncMock(return_value=None)
        await sync_channel_messages_async(client, channel, gid, since_date=since)

    asyncio.run(main())


@pytest.mark.django_db
def test_sync_channel_messages_async_last_synced_branch():
    gid = _uniq()
    cid = _uniq()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
        last_synced_at=django_timezone.now() - timedelta(hours=3),
    )

    async def main():
        client = MagicMock()
        client.get_channel = AsyncMock(return_value=None)
        await sync_channel_messages_async(client, channel, gid)

    asyncio.run(main())


@pytest.mark.django_db
def test_sync_channel_messages_async_default_window(monkeypatch):
    gid = _uniq()
    cid = _uniq()
    fixed_now = django_timezone.now()
    monkeypatch.setattr(django_timezone, "now", lambda: fixed_now)

    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
        last_synced_at=None,
    )

    async def main():
        client = MagicMock()
        client.get_channel = AsyncMock(return_value=None)
        await sync_channel_messages_async(client, channel, gid)

    asyncio.run(main())


@pytest.mark.django_db
def test_sync_channel_messages_async_process_batch_raises():
    gid = _uniq()
    cid = _uniq()
    server = DiscordServer.objects.create(server_id=gid, server_name="S", icon_url="")
    channel = DiscordChannel.objects.create(
        server=server,
        channel_id=cid,
        channel_name="c",
        channel_type="text",
    )

    async def main():
        client = MagicMock()
        dch = MagicMock()
        dch.name = "c"
        client.get_channel = AsyncMock(return_value=dch)
        client.fetch_messages_since = AsyncMock(return_value=[{"id": 1}])

        with patch.object(
            messages_mod,
            "_process_messages_in_batches",
            new_callable=AsyncMock,
            side_effect=ValueError("bad batch"),
        ):
            with pytest.raises(ValueError, match="bad batch"):
                await sync_channel_messages_async(client, channel, gid, full_sync=True)

    asyncio.run(main())
