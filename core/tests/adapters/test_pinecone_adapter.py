"""Unit tests for core.adapters.pinecone.PineconeAdapter."""

from unittest.mock import MagicMock, patch

import pytest

from core.adapters.pinecone import (
    PineconeAdapter,
    PineconeSdkIndexAdapter,
    ensure_pinecone_available,
)


pytest.importorskip("pinecone")


def test_ensure_pinecone_available_when_installed():
    ensure_pinecone_available()


def test_pinecone_adapter_from_api_key():
    with patch("core.adapters.pinecone.Pinecone") as mock_pc_cls:
        mock_pc = MagicMock()
        mock_pc_cls.return_value = mock_pc
        adapter = PineconeAdapter.from_api_key("pc-test")
    mock_pc_cls.assert_called_once_with(api_key="pc-test")
    assert adapter._pc is mock_pc


def test_pinecone_adapter_list_index_names():
    idx_a = MagicMock()
    idx_a.name = "dense"
    idx_b = MagicMock()
    idx_b.name = "dense-sparse"
    pc = MagicMock()
    pc.list_indexes.return_value = [idx_a, idx_b]
    adapter = PineconeAdapter(pc)
    assert adapter.list_index_names() == {"dense", "dense-sparse"}


def test_pinecone_adapter_create_index_for_model():
    pc = MagicMock()
    adapter = PineconeAdapter(pc)
    embed = {"model": "m", "field_map": {"text": "chunk_text"}}
    adapter.create_index_for_model(
        name="idx",
        cloud="aws",
        region="us-east-1",
        embed=embed,
    )
    pc.create_index_for_model.assert_called_once_with(
        name="idx",
        cloud="aws",
        region="us-east-1",
        embed=embed,
    )


def test_pinecone_sdk_index_adapter_forwards_calls():
    raw = MagicMock()
    idx = PineconeSdkIndexAdapter(raw)
    idx.upsert_records(records=[{"id": "1"}], namespace="ns")
    raw.upsert_records.assert_called_once_with(
        records=[{"id": "1"}],
        namespace="ns",
    )
    idx.update(id="1", set_metadata={"k": "v"}, namespace="ns")
    raw.update.assert_called_once_with(
        id="1",
        set_metadata={"k": "v"},
        namespace="ns",
    )
    idx.delete(ids=["1"], namespace="ns")
    raw.delete.assert_called_once_with(ids=["1"], namespace="ns")
    idx.describe_index_stats()
    raw.describe_index_stats.assert_called_once()
