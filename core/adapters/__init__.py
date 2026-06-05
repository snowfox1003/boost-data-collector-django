"""External platform adapter protocols and default implementations."""

from core.adapters.github import GitHubApiAdapter
from core.adapters.pinecone import (
    PineconeAdapter,
    PineconeSdkIndexAdapter,
    ensure_pinecone_available,
)
from core.adapters.protocols import (
    GitHubApiProtocol,
    PineconeClientProtocol,
    PineconeIndexProtocol,
    SlackWebApiProtocol,
)
from core.adapters.slack import SlackWebApiAdapter

__all__ = [
    "GitHubApiAdapter",
    "GitHubApiProtocol",
    "PineconeAdapter",
    "PineconeClientProtocol",
    "PineconeIndexProtocol",
    "PineconeSdkIndexAdapter",
    "SlackWebApiAdapter",
    "SlackWebApiProtocol",
    "ensure_pinecone_available",
]
