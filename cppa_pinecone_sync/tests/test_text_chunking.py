"""Tests for cppa_pinecone_sync.text_chunking (Document + RecursiveCharacterTextSplitter)."""

from cppa_pinecone_sync.text_chunking import Document, RecursiveCharacterTextSplitter


def test_split_documents_preserves_metadata_and_start_index():
    """Chunks inherit metadata and record ``start_index`` when ``add_start_index`` is True."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=80,
        chunk_overlap=10,
        length_function=len,
        add_start_index=True,
    )
    body = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod "
        "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam."
    )
    docs = [
        Document(
            page_content=body,
            metadata={"doc_id": "doc-1", "source_ids": "s1"},
        )
    ]
    out = splitter.split_documents(docs)
    assert len(out) >= 2
    for chunk in out:
        assert "start_index" in chunk.metadata
        assert chunk.metadata["doc_id"] == "doc-1"
        assert chunk.metadata["source_ids"] == "s1"
        assert len(chunk.page_content) <= 80


def test_split_text_empty():
    """Empty input yields no chunks."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=10, chunk_overlap=0)
    assert splitter.split_text("") == []


def test_chunk_overlap_must_not_exceed_chunk_size():
    """Constructor rejects overlap larger than chunk size."""
    try:
        RecursiveCharacterTextSplitter(chunk_size=10, chunk_overlap=20)
    except ValueError as e:
        assert "chunk overlap" in str(e).lower()
    else:
        raise AssertionError("expected ValueError")
