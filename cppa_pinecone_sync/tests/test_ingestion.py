"""Unit tests for ``cppa_pinecone_sync.ingestion.PineconeIngestion`` (in-tree ``Document``)."""

from unittest.mock import MagicMock, patch

import pytest
from django.test.utils import override_settings


from cppa_pinecone_sync.ingestion import PineconeIngestion
from cppa_pinecone_sync.types import PineconeInstance
from cppa_pinecone_sync.text_chunking import Document


pytest.importorskip("pinecone")


@pytest.fixture
def pinecone_settings():
    with override_settings(
        PINECONE_INDEX_NAME="idx-test",
        PINECONE_API_KEY="pc-test-key",
        PINECONE_PRIVATE_API_KEY="pc-private-key",
        PINECONE_BATCH_SIZE=2,
        PINECONE_CHUNK_SIZE=500,
        PINECONE_CHUNK_OVERLAP=50,
        PINECONE_MIN_TEXT_LENGTH=10,
        PINECONE_MIN_WORDS=2,
        PINECONE_UPDATE_MAX_WORKERS=1,
    ):
        yield


def _make_indexes():
    dense = MagicMock()
    sparse = MagicMock()
    dense.describe_index_stats.return_value = {
        "total_vector_count": 3,
        "dimension": 384,
        "index_fullness": 0.1,
        "namespaces": {"ns": {}},
    }
    sparse.describe_index_stats.return_value = {}
    return dense, sparse


def test_validate_config_missing_index_name(pinecone_settings):
    with override_settings(PINECONE_INDEX_NAME=""):
        ing = PineconeIngestion.__new__(PineconeIngestion)
        ing.index_name = ""
        ing.instance = PineconeInstance.PUBLIC
        ing._api_key = "k"
        with pytest.raises(ValueError, match="PINECONE_INDEX_NAME"):
            ing._validate_config()


def test_validate_config_missing_public_key(pinecone_settings):
    with override_settings(PINECONE_API_KEY=""):
        ing = PineconeIngestion.__new__(PineconeIngestion)
        ing.index_name = "x"
        ing.instance = PineconeInstance.PUBLIC
        ing._api_key = ""
        ing._private_api_key = "priv"
        with pytest.raises(ValueError, match="PINECONE_API_KEY"):
            ing._validate_config()


def test_validate_config_missing_private_key(pinecone_settings):
    with override_settings(PINECONE_PRIVATE_API_KEY=""):
        ing = PineconeIngestion.__new__(PineconeIngestion)
        ing.index_name = "x"
        ing.instance = PineconeInstance.PRIVATE
        ing._private_api_key = ""
        ing._api_key = "pub"
        with pytest.raises(ValueError, match="PINECONE_PRIVATE_API_KEY"):
            ing._validate_config()


def test_is_valid_chunk_and_helpers(pinecone_settings):
    ing = PineconeIngestion()
    assert ing._is_valid_chunk("") is False
    assert ing._is_valid_chunk("x" * 5) is False
    long_ok = "This is a valid chunk with enough words and length for the indexer here."
    assert ing._is_valid_chunk(long_ok) is True
    assert ing._is_table_separator("| --- | --- |") is True
    fmt_heavy = "|-- :: " * 30
    assert ing._is_mostly_formatting(fmt_heavy) is True


def test_build_hashed_doc_id_with_start_index(pinecone_settings):
    ing = PineconeIngestion()
    doc_id = ing._build_hashed_doc_id(
        metadata={"doc_id": "d1", "start_index": 10},
        text="hello world",
        batch_start_idx=0,
        record_idx=0,
    )
    assert len(doc_id) == 32


def test_empty_upsert_update_delete(pinecone_settings):
    ing = PineconeIngestion()
    dense, sparse = _make_indexes()
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True
    ing.pc = MagicMock()

    assert ing.upsert_documents([])["upserted"] == 0
    assert ing.update_documents([])["updated"] == 0
    assert ing.delete_documents([])["deleted"] == 0
    dense.upsert_records.assert_not_called()


def test_upsert_documents_batches_and_skips_invalid_chunks(pinecone_settings):
    ing = PineconeIngestion()

    dense = MagicMock()
    sparse = MagicMock()
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True

    docs = [
        Document(page_content="too short"),
        Document(
            page_content=(
                "Alpha beta gamma delta epsilon zeta eta theta enough words "
                "here for minimum length and word count rules."
            ),
            metadata={"title": "T"},
        ),
    ]
    with patch.object(ing, "_ensure_indexes_ready"):
        out = ing.upsert_documents(docs, namespace="ns", is_chunked=True)
    assert out["total"] == 2
    assert out["upserted"] >= 1
    dense.upsert_records.assert_called()
    sparse.upsert_records.assert_called()


def test_upsert_batch_failure_records_error(pinecone_settings):
    ing = PineconeIngestion()
    dense = MagicMock()
    dense.upsert_records.side_effect = RuntimeError("boom")
    sparse = MagicMock()
    ing.dense_index = dense
    ing.sparse_index = sparse

    doc = Document(
        page_content=(
            "One two three four five six seven eight nine ten eleven twelve "
            "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty."
        ),
        metadata={"doc_id": "x"},
    )
    with patch.object(ing, "_ensure_indexes_ready"):
        out = ing.upsert_documents([doc], is_chunked=True)
    assert out["errors"]
    assert out["failed_documents"]


def test_update_documents_parallel_path(pinecone_settings):
    with override_settings(PINECONE_UPDATE_MAX_WORKERS=4):
        ing = PineconeIngestion()

    dense = MagicMock()
    sparse = MagicMock()
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True

    body = (
        "aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp qq rr ss tt uu vv "
        "ww xx yy zz words here."
    )
    docs = [
        Document(page_content=body, metadata={"source_ids": "s1"}),
        Document(page_content=body + " extra", metadata={"table_ids": "t2"}),
    ]
    with patch.object(ing, "_ensure_indexes_ready"):
        out = ing.update_documents(docs, is_chunked=True)
    assert out["updated"] == 2


def test_update_single_record_failure_logged(pinecone_settings):
    dense = MagicMock()
    dense.update.side_effect = ValueError("no")
    with pytest.raises(ValueError):
        PineconeIngestion._update_index_record(dense, "id1", {"k": "v"}, "ns", "dense")


def test_delete_batch_failure(pinecone_settings):
    ing = PineconeIngestion()
    dense = MagicMock()
    dense.delete.side_effect = RuntimeError("del fail")
    sparse = MagicMock()
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True
    with patch.object(ing, "_ensure_indexes_ready"):
        out = ing.delete_documents(["a"], namespace="n")
    assert out["errors"]
    assert out["deleted"] == 0


def test_get_index_stats_error_returns_empty(pinecone_settings):
    ing = PineconeIngestion()
    dense = MagicMock()
    dense.describe_index_stats.side_effect = RuntimeError("stats down")
    sparse = MagicMock()
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True

    with patch.object(ing, "_ensure_indexes_ready"):
        stats = ing.get_index_stats()
    assert "error" in stats


def test_format_single_index_stats():
    empty = PineconeIngestion._format_single_index_stats({})
    assert empty["total_vectors"] == 0


def test_ensure_pinecone_client_connection_error(pinecone_settings):
    ing = PineconeIngestion()
    with patch("cppa_pinecone_sync.ingestion.Pinecone") as MockPC:
        MockPC.side_effect = RuntimeError("bad key")
        ing._pc_initialized = False
        with pytest.raises(ConnectionError, match="Cannot connect"):
            ing._ensure_pinecone_client()


def test_get_or_create_indexes_connect_existing(pinecone_settings):
    ing = PineconeIngestion()
    idx_main = MagicMock()
    idx_main.name = "idx-test"
    idx_sparse = MagicMock()
    idx_sparse.name = "idx-test-sparse"
    pc = MagicMock()
    pc.list_indexes.return_value = [idx_main, idx_sparse]
    idx_dense_obj = MagicMock()
    idx_sparse_obj = MagicMock()
    pc.Index.side_effect = [idx_dense_obj, idx_sparse_obj]
    ing.pc = pc
    ing._pc_initialized = True
    ing._dense_index_initialized = False
    ing._sparse_index_initialized = False

    ing._get_or_create_indexes()
    assert ing.dense_index is idx_dense_obj
    assert ing.sparse_index is idx_sparse_obj


def test_create_new_indexes_invalid_region(pinecone_settings):
    ing = PineconeIngestion()
    pc = MagicMock()
    pc.create_index_for_model.side_effect = Exception("NOT_FOUND xyz")
    ing.pc = pc
    with pytest.raises(ValueError, match="Invalid Pinecone region"):
        ing._create_new_indexes(set(), "idx-test", "idx-test-sparse")


def test_prepare_batch_records_empty_when_all_invalid(pinecone_settings):
    ing = PineconeIngestion()
    batch = [Document(page_content="nope")]
    assert ing._prepare_batch_records(batch, 0) == []


def test_upsert_all_batches_no_valid_records_warning(pinecone_settings):
    ing = PineconeIngestion()
    docs = [Document(page_content="short")]
    total, errors, failed = ing._upsert_all_batches(docs, None)
    assert total == 0
    assert not errors


def test_get_index_stats_success(pinecone_settings):
    ing = PineconeIngestion()
    dense = MagicMock()
    dense.describe_index_stats.return_value = {"total_vector_count": 1}
    sparse = MagicMock()
    sparse.describe_index_stats.return_value = {"total_vector_count": 2}
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True
    with patch.object(ing, "_ensure_indexes_ready"):
        stats = ing.get_index_stats()
    assert "dense_index" in stats and "error" not in stats


def test_create_new_indexes_success(pinecone_settings):
    ing = PineconeIngestion()
    pc = MagicMock()
    pc.list_indexes.return_value = []
    pc.Index.side_effect = lambda name: MagicMock(name=name)
    ing.pc = pc
    ing._create_new_indexes(set(), "idx-test", "idx-test-sparse")
    assert ing.dense_index is not None
    pc.create_index_for_model.assert_called()


def test_update_documents_sequential_failure_counts(pinecone_settings):
    ing = PineconeIngestion()
    dense = MagicMock()
    dense.update.side_effect = RuntimeError("metadata")
    sparse = MagicMock()
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True
    body = (
        "aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp qq rr ss tt uu vv "
        "ww xx yy zz words here."
    )
    doc = Document(page_content=body, metadata={"doc_id": "d1"})
    with patch.object(ing, "_ensure_indexes_ready"):
        out = ing.update_documents([doc], is_chunked=True)
    assert out["errors"]
    assert out["updated"] == 0


def test_update_documents_parallel_failure(pinecone_settings):
    with override_settings(PINECONE_UPDATE_MAX_WORKERS=4):
        ing = PineconeIngestion()
    dense = MagicMock()
    dense.update.side_effect = RuntimeError("up")
    sparse = MagicMock()
    ing.dense_index = dense
    ing.sparse_index = sparse
    ing._dense_index_initialized = True
    ing._sparse_index_initialized = True
    body = (
        "aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp qq rr ss tt uu vv "
        "ww xx yy zz words here."
    )
    doc = Document(page_content=body, metadata={"doc_id": "d2"})
    with patch.object(ing, "_ensure_indexes_ready"):
        out = ing.update_documents([doc], is_chunked=True)
    assert out["errors"]
