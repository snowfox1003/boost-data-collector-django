"""Tests for cppa_pinecone_sync.sync_api cross-app surface."""

from cppa_pinecone_sync import sync_api


def test_sync_api_exports_sync_to_pinecone():
    assert callable(sync_api.sync_to_pinecone)


def test_sync_api_exports_pinecone_instance():
    assert sync_api.PineconeInstance is not None


def test_sync_api_exports_preprocess_fn_type():
    # PreprocessFn is a type alias; ensure it is exported for typing in callers.
    assert "PreprocessFn" in sync_api.__all__
