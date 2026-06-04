"""Test doubles for core.adapters protocols."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


class FakePineconeIndex:
    """In-memory index double implementing PineconeIndexProtocol."""

    def __init__(self, name: str = "fake-index") -> None:
        self.name = name
        self.upsert_records = MagicMock()
        self.update = MagicMock()
        self.delete = MagicMock()
        self.describe_index_stats = MagicMock(
            return_value={
                "total_vector_count": 0,
                "dimension": 384,
                "index_fullness": 0.0,
                "namespaces": {},
            }
        )


class FakePineconeClient:
    """In-memory client double implementing PineconeClientProtocol."""

    def __init__(
        self,
        *,
        index_names: set[str] | None = None,
        create_error: Exception | None = None,
        connect_error: Exception | None = None,
    ) -> None:
        self._index_names = set(index_names) if index_names is not None else set()
        self._indexes: dict[str, FakePineconeIndex] = {}
        self.create_index_for_model_mock = MagicMock(
            side_effect=self._create_index_for_model_impl
        )
        self._create_error = create_error
        self._connect_error = connect_error

    def _create_index_for_model_impl(self, **kwargs: Any) -> None:
        if self._create_error is not None:
            raise self._create_error
        name = kwargs.get("name")
        if name:
            self._index_names.add(name)

    def list_index_names(self) -> set[str]:
        return set(self._index_names)

    def create_index_for_model(
        self,
        *,
        name: str,
        cloud: str,
        region: str,
        embed: dict[str, Any],
    ) -> None:
        self.create_index_for_model_mock(
            name=name,
            cloud=cloud,
            region=region,
            embed=embed,
        )

    def get_index(self, name: str) -> FakePineconeIndex:
        if self._connect_error is not None:
            raise self._connect_error
        if name not in self._indexes:
            self._indexes[name] = FakePineconeIndex(name=name)
        return self._indexes[name]
