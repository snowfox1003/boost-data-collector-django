"""
Pinecone SDK adapter — sole ``pinecone`` import site in the repository.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.adapters.protocols import PineconeIndexProtocol

try:
    from pinecone import Pinecone
except ImportError as e:
    Pinecone = None  # type: ignore[assignment,misc]
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


def ensure_pinecone_available() -> None:
    """Raise ImportError when the pinecone package is not installed."""
    if _IMPORT_ERROR is not None:
        raise ImportError(
            "Missing dependencies for Pinecone adapter. "
            "Install with: pip install pinecone"
        ) from _IMPORT_ERROR


class PineconeSdkIndexAdapter:
    """Wraps a pinecone Index handle behind :class:`PineconeIndexProtocol`."""

    def __init__(self, index: Any) -> None:
        self._index = index

    def upsert_records(
        self,
        *,
        records: list[dict[str, Any]],
        namespace: str | None,
    ) -> None:
        self._index.upsert_records(records=records, namespace=namespace)

    def update(
        self,
        *,
        id: str,
        set_metadata: dict[str, Any],
        namespace: str | None,
    ) -> None:
        self._index.update(id=id, set_metadata=set_metadata, namespace=namespace)

    def delete(
        self,
        *,
        ids: list[str],
        namespace: str | None,
    ) -> None:
        self._index.delete(ids=ids, namespace=namespace)

    def describe_index_stats(self) -> dict[str, Any]:
        return self._index.describe_index_stats()


class PineconeAdapter:
    """Production Pinecone client implementing :class:`PineconeClientProtocol`."""

    def __init__(self, pc: Any) -> None:
        self._pc = pc

    @classmethod
    def from_api_key(cls, api_key: str) -> PineconeAdapter:
        ensure_pinecone_available()
        if Pinecone is None:
            raise RuntimeError("Pinecone SDK unavailable after import check")
        return cls(Pinecone(api_key=api_key))

    def list_index_names(self) -> set[str]:
        return {idx.name for idx in self._pc.list_indexes()}

    def create_index_for_model(
        self,
        *,
        name: str,
        cloud: str,
        region: str,
        embed: Mapping[str, Any],
    ) -> None:
        self._pc.create_index_for_model(
            name=name,
            cloud=cloud,
            region=region,
            embed=dict(embed),
        )

    def get_index(self, name: str) -> PineconeIndexProtocol:
        return PineconeSdkIndexAdapter(self._pc.Index(name))
