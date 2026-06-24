"""Pyright-positive sample: structural conformance to :class:`core.concurrency.ConcurrencySlot`."""

from __future__ import annotations

import threading

from core.concurrency import ConcurrencySlot


def sample_concurrency_slot() -> ConcurrencySlot:
    return threading.BoundedSemaphore(3)
