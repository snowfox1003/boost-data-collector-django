"""
Stable adapter protocols for external platform APIs.

These protocols sit below per-app Pydantic boundary schemas and above vendor SDKs
or HTTP clients. Implementations live in sibling modules under ``core.adapters``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Union, runtime_checkable


@runtime_checkable
class PineconeIndexProtocol(Protocol):
    """Vector index operations used by Pinecone ingestion."""

    def upsert_records(
        self,
        *,
        records: list[dict[str, Any]],
        namespace: str | None,
    ) -> None: ...

    def update(
        self,
        *,
        id: str,
        set_metadata: dict[str, Any],
        namespace: str | None,
    ) -> None: ...

    def delete(
        self,
        *,
        ids: list[str],
        namespace: str | None,
    ) -> None: ...

    def describe_index_stats(self) -> dict[str, Any]: ...


@runtime_checkable
class PineconeClientProtocol(Protocol):
    """Pinecone control-plane and index handle factory."""

    def list_index_names(self) -> set[str]: ...

    def create_index_for_model(
        self,
        *,
        name: str,
        cloud: str,
        region: str,
        embed: Mapping[str, Any],
    ) -> None: ...

    def get_index(self, name: str) -> PineconeIndexProtocol: ...


@runtime_checkable
class SlackWebApiProtocol(Protocol):
    """Slack Web API methods used by collectors and slack_ops."""

    def conversations_list(
        self,
        types: str = "public_channel",
        exclude_archived: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> dict: ...

    def conversations_join(self, channel: str) -> dict: ...

    def conversations_info(self, channel: str) -> dict: ...

    def conversations_members(
        self,
        channel: str,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> dict: ...

    def conversations_history(
        self,
        channel: str,
        limit: int = 100,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> dict: ...

    def users_info(self, user: str) -> dict: ...

    def users_list(
        self,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> dict: ...

    def team_info(self) -> dict: ...

    def auth_test(self) -> dict: ...

    def files_info(
        self,
        file: str,
        timeout: int = 30,
    ) -> dict: ...


@runtime_checkable
class GitHubApiProtocol(Protocol):
    """GitHub REST/GraphQL methods used by github_activity_tracker and consumers."""

    @property
    def rate_limit_remaining(self) -> int | None: ...

    @property
    def rate_limit_reset_time(self) -> int | None: ...

    def rest_request(self, endpoint: str, params: Optional[dict] = None) -> dict: ...

    def rest_request_with_link(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> tuple[Union[list, dict], Optional[str]]: ...

    def rest_request_conditional_with_link(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        etag: Optional[str] = None,
    ) -> tuple[Optional[dict], Optional[str], Optional[str]]: ...

    def rest_request_conditional_with_all_links(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        etag: Optional[str] = None,
    ) -> tuple[Optional[Union[list, dict]], Optional[str], dict[str, str]]: ...

    def rest_request_url(
        self, full_url: str
    ) -> tuple[Union[list, dict], Optional[str]]: ...

    def get_repository_info(self, owner: str, repo: str) -> dict: ...

    def graphql_request(
        self,
        query: str,
        variables: Optional[dict] = None,
    ) -> dict: ...
