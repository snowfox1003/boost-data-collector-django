"""
JSON file persistence for the PR bot job queue and rate-limit state.

State file layout:
  { "postedAt": [<unix_timestamp>, ...], "queue": [<job_dict>, ...] }

When team_id is provided, state is stored in state_<team_id>.json for multi-workspace support.
"""

import json
import logging
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Generator, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

import portalocker

logger = logging.getLogger(__name__)

_DEFAULT_STATE: dict[str, Any] = {"postedAt": [], "queue": []}

_team_thread_locks: dict[str, threading.Lock] = {}
_team_thread_locks_guard = threading.Lock()


def _thread_lock_for(team_id: Optional[str]) -> threading.Lock:
    """In-process mutex paired with the file lock (required for reliable Windows locking)."""
    key = _get_lock_file_path(team_id)
    with _team_thread_locks_guard:
        lock = _team_thread_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _team_thread_locks[key] = lock
        return lock


def _sanitize_team_id_for_path(team_id: str) -> str:
    """Safe filename segment from Slack team_id (e.g. T01234ABCD -> T01234ABCD)."""
    if not team_id:
        return "default"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", team_id)


def _get_state_file_path(team_id: Optional[str] = None) -> str:
    """Resolve the state file path. If team_id is None, state.json; else state_<team_id>.json."""
    from slack_event_handler.workspace import get_data_dir

    data_dir = get_data_dir()
    if team_id:
        safe = _sanitize_team_id_for_path(team_id)
        return str(data_dir / f"state_{safe}.json")
    return str(data_dir / "state.json")


def _get_lock_file_path(team_id: Optional[str] = None) -> str:
    """Resolve the advisory lock file path (sibling of the state JSON file)."""
    return f"{_get_state_file_path(team_id)}.lock"


@contextmanager
def state_file_lock(team_id: Optional[str] = None) -> Generator[None, None, None]:
    """Exclusive advisory lock for per-team state read-modify-write critical sections."""
    with _thread_lock_for(team_id):
        lock_path = _get_lock_file_path(team_id)
        _ensure_dir(lock_path)
        if fcntl is not None:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        else:
            with portalocker.Lock(lock_path, timeout=-1):
                yield


@contextmanager
def modify_state(
    team_id: Optional[str] = None,
) -> Generator[dict[str, Any], None, None]:
    """Load state under lock, yield for mutation, then save before releasing the lock."""
    with state_file_lock(team_id):
        state = load_state(team_id)
        yield state
        save_state(state, team_id)


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def load_state(team_id: Optional[str] = None) -> dict[str, Any]:
    """Load state for the given team. team_id=None uses state.json (single-workspace)."""
    path = _get_state_file_path(team_id)
    _ensure_dir(path)
    if not os.path.exists(path):
        return deepcopy(_DEFAULT_STATE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.exception("Corrupt state file decoding %s", path)
        quarantine = f"{path}.corrupt.{int(time.time())}"
        try:
            os.replace(path, quarantine)
        except OSError as e:
            logger.warning("Could not quarantine %s to %s: %s", path, quarantine, e)
        return deepcopy(_DEFAULT_STATE)


def save_state(state: dict[str, Any], team_id: Optional[str] = None) -> None:
    """Save state for the given team. team_id=None uses state.json (single-workspace)."""
    path = _get_state_file_path(team_id)
    _ensure_dir(path)
    dir_path = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dir_path,
        delete=False,
        suffix=".tmp",
    ) as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        temp_path = f.name
    os.replace(temp_path, path)
