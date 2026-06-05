"""
GitHub REST/GraphQL adapter — delegates to :class:`core.operations.github_ops.client.GitHubAPIClient`.
"""

from __future__ import annotations

from typing import Optional, Union

from core.operations.github_ops.client import GitHubAPIClient


class GitHubApiAdapter:
    """Stable GitHub API surface; wraps :class:`GitHubAPIClient`."""

    def __init__(
        self,
        client: GitHubAPIClient | None = None,
        *,
        token: str | None = None,
    ) -> None:
        if client is not None and token is not None:
            raise ValueError("Pass either client or token, not both")
        if client is None:
            if not token:
                raise ValueError("token is required when client is not provided")
            client = GitHubAPIClient(token)
        self._client = client

    @property
    def rate_limit_remaining(self) -> int | None:
        return self._client.rate_limit_remaining

    @property
    def rate_limit_reset_time(self) -> int | None:
        return self._client.rate_limit_reset_time

    def rest_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        return self._client.rest_request(endpoint, params=params)

    def rest_request_with_link(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> tuple[Union[list, dict], Optional[str]]:
        return self._client.rest_request_with_link(endpoint, params=params)

    def rest_request_conditional_with_link(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        etag: Optional[str] = None,
    ) -> tuple[Optional[dict], Optional[str], Optional[str]]:
        return self._client.rest_request_conditional_with_link(
            endpoint,
            params=params,
            etag=etag,
        )

    def rest_request_conditional_with_all_links(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        etag: Optional[str] = None,
    ) -> tuple[Optional[Union[list, dict]], Optional[str], dict[str, str]]:
        return self._client.rest_request_conditional_with_all_links(
            endpoint,
            params=params,
            etag=etag,
        )

    def rest_request_url(
        self, full_url: str
    ) -> tuple[Union[list, dict], Optional[str]]:
        return self._client.rest_request_url(full_url)

    def get_repository_info(self, owner: str, repo: str) -> dict:
        return self._client.get_repository_info(owner, repo)

    def graphql_request(
        self,
        query: str,
        variables: Optional[dict] = None,
    ) -> dict:
        return self._client.graphql_request(query, variables=variables)
