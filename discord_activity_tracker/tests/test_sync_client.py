"""Tests for discord_activity_tracker.sync.client.DiscordSyncClient."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discord_activity_tracker.sync.client import (
    DiscordSyncClient,
    discord_message_to_sync_dict,
    run_async,
)


@pytest.fixture
def mock_discord_pkg():
    with patch("discord_activity_tracker.sync.client.discord") as m:
        m.NotFound = type("NotFound", (Exception,), {})
        m.Forbidden = type("Forbidden", (Exception,), {})
        m.HTTPException = type("HTTPException", (Exception,), {})
        m.TextChannel = type("TextChannel", (), {})
        m.Intents.default.return_value = MagicMock()
        inner = MagicMock()
        inner.login = AsyncMock()
        inner.close = AsyncMock()
        m.Client.return_value = inner
        yield m, inner


def test_init_registers_client(mock_discord_pkg):
    _, inner = mock_discord_pkg
    c = DiscordSyncClient("tok")
    assert c.token == "tok"
    assert c.client is inner
    assert c._ready is False


def test_ensure_ready_logs_in_once(mock_discord_pkg):
    _, inner = mock_discord_pkg
    inner.login = AsyncMock()

    async def main():
        c = DiscordSyncClient("tok")
        await c._ensure_ready()
        await c._ensure_ready()

    asyncio.run(main())
    inner.login.assert_called_once_with("tok")


def test_get_guild_not_found(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.fetch_guild = AsyncMock(side_effect=m.NotFound())

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_guild(99)

    assert asyncio.run(main()) is None


def test_get_guild_forbidden(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.fetch_guild = AsyncMock(side_effect=m.Forbidden())

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_guild(99)

    assert asyncio.run(main()) is None


def test_get_channels_empty_when_no_guild(mock_discord_pkg):
    _, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.fetch_guild = AsyncMock(return_value=None)

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_channels(1)

    assert asyncio.run(main()) == []


def test_get_channels_filters_text_only(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    guild = MagicMock()
    guild.name = "G"
    tc = MagicMock(spec=m.TextChannel)
    vc = MagicMock()
    inner.fetch_guild = AsyncMock(return_value=guild)
    guild.fetch_channels = AsyncMock(return_value=[tc, vc])

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_channels(1)

    assert asyncio.run(main()) == [tc]


def test_get_channels_fetch_raises(mock_discord_pkg):
    _, inner = mock_discord_pkg
    inner.login = AsyncMock()
    guild = MagicMock()
    inner.fetch_guild = AsyncMock(return_value=guild)
    guild.fetch_channels = AsyncMock(side_effect=RuntimeError("network"))

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_channels(1)

    assert asyncio.run(main()) == []


def test_get_channel_success(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    tc = MagicMock(spec=m.TextChannel)
    inner.fetch_channel = AsyncMock(return_value=tc)

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_channel(10)

    assert asyncio.run(main()) is tc


def test_get_channel_wrong_type(mock_discord_pkg):
    _, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.fetch_channel = AsyncMock(return_value=MagicMock())

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_channel(10)

    assert asyncio.run(main()) is None


def test_get_channel_not_found(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.fetch_channel = AsyncMock(side_effect=m.NotFound())

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_channel(10)

    assert asyncio.run(main()) is None


def test_get_channel_forbidden(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.fetch_channel = AsyncMock(side_effect=m.Forbidden())

    async def main():
        c = DiscordSyncClient("tok")
        return await c.get_channel(10)

    assert asyncio.run(main()) is None


def test_fetch_messages_since_collects(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()

    msg = MagicMock()
    msg.id = 1
    msg.content = "hi"
    msg.author.id = 9
    msg.author.name = "u"
    msg.author.display_name = "U"
    msg.author.bot = False
    msg.author.avatar = None
    msg.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    msg.edited_at = None
    msg.reference = None
    msg.attachments = []
    msg.reactions = []

    ch = MagicMock(spec=m.TextChannel)
    ch.name = "general"

    async def hist(**_kwargs):
        yield msg

    ch.history = hist

    async def main():
        c = DiscordSyncClient("tok")
        return await c.fetch_messages_since(ch)

    out = asyncio.run(main())
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_fetch_messages_since_forbidden(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    ch = MagicMock(spec=m.TextChannel)
    ch.name = "x"

    async def hist(**_kwargs):
        raise m.Forbidden()
        yield  # pragma: no cover

    ch.history = hist

    async def main():
        c = DiscordSyncClient("tok")
        return await c.fetch_messages_since(ch)

    assert asyncio.run(main()) == []


def test_fetch_messages_since_http_exception(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    ch = MagicMock(spec=m.TextChannel)
    ch.name = "x"

    async def hist(**_kwargs):
        raise m.HTTPException()
        yield  # pragma: no cover

    ch.history = hist

    async def main():
        c = DiscordSyncClient("tok")
        return await c.fetch_messages_since(ch)

    assert asyncio.run(main()) == []


def test_fetch_messages_since_logs_every_100_messages(mock_discord_pkg):
    m, inner = mock_discord_pkg
    ch = MagicMock(spec=m.TextChannel)
    ch.name = "logs-here"

    async def hist(**_kwargs):
        for i in range(100):
            msg = MagicMock()
            msg.id = i
            msg.content = ""
            msg.author = SimpleNamespace(
                id=1, name="u", display_name="u", bot=False, avatar=None
            )
            msg.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            msg.edited_at = None
            msg.reference = None
            msg.attachments = []
            msg.reactions = []
            yield msg

    ch.history = hist

    async def main():
        c = DiscordSyncClient("tok")
        return await c.fetch_messages_since(ch)

    assert len(asyncio.run(main())) == 100


def test_fetch_messages_since_unexpected_error(mock_discord_pkg):
    m, inner = mock_discord_pkg
    inner.login = AsyncMock()
    ch = MagicMock(spec=m.TextChannel)
    ch.name = "x"

    async def hist(**_kwargs):
        raise ValueError("weird")
        yield  # pragma: no cover

    ch.history = hist

    async def main():
        c = DiscordSyncClient("tok")
        return await c.fetch_messages_since(ch)

    assert asyncio.run(main()) == []


def test_close_ready(mock_discord_pkg):
    _, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.close = AsyncMock()

    async def main():
        c = DiscordSyncClient("tok")
        await c._ensure_ready()
        await c.close()

    asyncio.run(main())
    inner.close.assert_awaited_once()


def test_context_manager_calls_close(mock_discord_pkg):
    _, inner = mock_discord_pkg
    inner.login = AsyncMock()
    inner.close = AsyncMock()

    # __exit__ calls shutdown_sync(); without .run() there is no dedicated loop,
    # so shutdown_sync falls back to run_async(close()). The coroutine must be
    # awaited — use wraps=real run_async instead of a bare MagicMock.
    import discord_activity_tracker.sync.client as client_module

    real_run_async = client_module.run_async
    with patch.object(client_module, "run_async", wraps=real_run_async) as ra:
        with DiscordSyncClient("tok") as c:
            c._ready = True
    ra.assert_called_once()
    inner.close.assert_awaited_once()


def test_run_async_returns_coroutine_result():
    """run_async must use a fresh event loop (not the deprecated get_event_loop)."""

    async def coro():
        return 42

    assert run_async(coro()) == 42


def test_run_async_does_not_use_get_event_loop():
    """Ensure run_async never calls the deprecated asyncio.get_event_loop."""

    async def coro():
        return 99

    with patch(
        "discord_activity_tracker.sync.client.asyncio.get_event_loop"
    ) as mock_gel:
        result = run_async(coro())

    # get_event_loop should never be touched
    mock_gel.assert_not_called()
    assert result == 99


def test_run_async_closes_loop_on_exception():
    """Loop must be closed even if the coroutine raises."""

    async def failing():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async(failing())


def test_discord_sync_client_run_reuses_event_loop(mock_discord_pkg):
    """All work on one client instance must share one loop (discord.py / aiohttp)."""
    loops: list = []

    async def record_loop():
        loops.append(asyncio.get_running_loop())
        return 1

    c = DiscordSyncClient("tok")
    c.run(record_loop())
    c.run(record_loop())
    assert len(loops) == 2
    assert loops[0] is loops[1]
    c.shutdown_sync()


def test_message_to_dict_with_attachment_and_reaction(mock_discord_pkg):
    msg = MagicMock()
    msg.id = 5
    msg.content = "c"
    msg.author = SimpleNamespace(
        id=1, name="n", display_name="n", bot=False, avatar=None
    )
    msg.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    msg.edited_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    msg.reference = MagicMock(message_id=99)

    att = MagicMock()
    att.url = "http://f"
    att.filename = "f.txt"
    att.size = 3
    msg.attachments = [att]

    react = MagicMock()
    react.emoji = "👍"
    react.count = 2
    msg.reactions = [react]

    msg.type = SimpleNamespace(name="default")
    msg.pinned = False

    d = discord_message_to_sync_dict(msg)
    assert d["author"]["display_name"] == "n"
    assert d["message_type"] == "Default"
    assert d["is_pinned"] is False
    assert d["attachments"][0]["filename"] == "f.txt"
    assert d["reactions"][0]["count"] == 2


def test_message_to_dict_reply_and_pinned(mock_discord_pkg):
    msg = MagicMock()
    msg.id = 1
    msg.content = ""
    msg.author = SimpleNamespace(
        id=1, name="u", display_name="u", bot=False, avatar=None
    )
    msg.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    msg.edited_at = None
    msg.reference = None
    msg.attachments = []
    msg.reactions = []
    msg.type = SimpleNamespace(name="reply")
    msg.pinned = True

    d = discord_message_to_sync_dict(msg)
    assert d["message_type"] == "Reply"
    assert d["is_pinned"] is True
