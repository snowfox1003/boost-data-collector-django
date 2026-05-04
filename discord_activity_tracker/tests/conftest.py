"""Discord tracker tests: stub discord.py when optional dependency is missing."""

import sys
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.filterwarnings(
    "ignore:coroutine 'DiscordSyncClient.close' was never awaited:RuntimeWarning"
)

try:
    import discord as _discord_check  # noqa: F401
except ImportError:
    _stub = MagicMock()
    for _exc in ("NotFound", "Forbidden", "HTTPException"):
        setattr(_stub, _exc, type(_exc, (Exception,), {}))
    _stub.TextChannel = type("TextChannel", (), {})
    _stub.Guild = type("Guild", (), {})
    _stub.Message = type("Message", (), {})
    _stub.Intents.default.return_value = MagicMock()
    _stub.Client.return_value = MagicMock()
    sys.modules["discord"] = _stub
