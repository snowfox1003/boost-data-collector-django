"""
Slack Web API adapter — delegates to :class:`core.operations.slack_ops.client.SlackAPIClient`.
"""

from __future__ import annotations

from typing import Optional

from core.operations.slack_ops.client import SlackAPIClient


class SlackWebApiAdapter:
    """Stable Slack Web API surface; wraps :class:`SlackAPIClient`."""

    def __init__(
        self,
        client: SlackAPIClient | None = None,
        *,
        bot_token: str | None = None,
    ) -> None:
        if client is not None and bot_token is not None:
            raise ValueError("Pass either client or bot_token, not both")
        if client is None:
            if not bot_token:
                raise ValueError("bot_token is required when client is not provided")
            client = SlackAPIClient(bot_token)
        self._client = client

    def conversations_list(
        self,
        types: str = "public_channel",
        exclude_archived: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> dict:
        return self._client.conversations_list(
            types=types,
            exclude_archived=exclude_archived,
            limit=limit,
            cursor=cursor,
        )

    def conversations_join(self, channel: str) -> dict:
        return self._client.conversations_join(channel)

    def conversations_info(self, channel: str) -> dict:
        return self._client.conversations_info(channel)

    def conversations_members(
        self,
        channel: str,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> dict:
        return self._client.conversations_members(
            channel=channel,
            limit=limit,
            cursor=cursor,
        )

    def conversations_history(
        self,
        channel: str,
        limit: int = 100,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> dict:
        return self._client.conversations_history(
            channel=channel,
            limit=limit,
            oldest=oldest,
            latest=latest,
            cursor=cursor,
        )

    def users_info(self, user: str) -> dict:
        return self._client.users_info(user)

    def users_list(
        self,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> dict:
        return self._client.users_list(limit=limit, cursor=cursor)

    def team_info(self) -> dict:
        return self._client.team_info()

    def auth_test(self) -> dict:
        return self._client.auth_test()

    def files_info(
        self,
        file: str,
        timeout: int = 30,
    ) -> dict:
        return self._client.files_info(file=file, timeout=timeout)
