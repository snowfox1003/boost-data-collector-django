"""Shared value types for cppa_pinecone_sync."""

from __future__ import annotations

from enum import Enum


class PineconeInstance(str, Enum):
    """Selects which Pinecone API key to use."""

    PUBLIC = "public"
    PRIVATE = "private"

    @classmethod
    def coerce(cls, instance: PineconeInstance | str | None) -> PineconeInstance:
        """Normalize *instance* to a ``PineconeInstance`` member."""
        if instance is None:
            return cls.PUBLIC
        if isinstance(instance, cls):
            return instance
        if isinstance(instance, str):
            try:
                return cls(instance.strip().lower())
            except ValueError as exc:
                raise ValueError("instance must be 'public' or 'private'.") from exc
        raise TypeError("instance must be PineconeInstance, str, or None.")
