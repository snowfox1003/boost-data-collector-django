"""
Structural protocols for in-process synchronization primitives.

These types complement the topology documented in :doc:`docs/CONCURRENCY.md`.
Concurrency manager classes own locks/semaphores; protocols describe the
contract their public surfaces expose to callers and type checkers.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, TypeVar

_T_co = TypeVar("_T_co", covariant=True)


class ConcurrencySlot(Protocol):
    """Context manager that serializes or bounds parallel work (lock/semaphore)."""

    def __enter__(self) -> bool | None: ...

    def __exit__(
        self,
        t: type[BaseException] | None,
        v: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class ThreadLocalStore(Protocol[_T_co]):
    """Per-thread resource holder; safe for concurrent access from multiple threads."""

    def get_for_thread(self, key: str) -> _T_co: ...
