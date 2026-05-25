"""Tests for cppa_pinecone_sync.types."""

import pytest

from cppa_pinecone_sync.types import PineconeInstance


def test_coerce_defaults_to_public():
    assert PineconeInstance.coerce(None) == PineconeInstance.PUBLIC


def test_coerce_accepts_enum():
    assert PineconeInstance.coerce(PineconeInstance.PRIVATE) == PineconeInstance.PRIVATE


def test_coerce_normalizes_string():
    assert PineconeInstance.coerce("PRIVATE") == PineconeInstance.PRIVATE


def test_coerce_rejects_invalid_string():
    with pytest.raises(ValueError, match="instance must be 'public' or 'private'"):
        PineconeInstance.coerce("staging")


def test_coerce_rejects_invalid_type():
    with pytest.raises(
        TypeError, match="instance must be PineconeInstance, str, or None"
    ):
        PineconeInstance.coerce(42)
