"""
Cross-app Pinecone sync API.

Other tracker apps must import orchestration from this module only — not
``sync``, ``ingestion``, or ``services`` directly.
"""

from __future__ import annotations

from cppa_pinecone_sync.sync import PreprocessFn, sync_to_pinecone
from cppa_pinecone_sync.types import PineconeInstance

__all__ = [
    "PineconeInstance",
    "PreprocessFn",
    "sync_to_pinecone",
]
