"""
Rolling-window rate limiter for the Slack PR comment bot.
Rate limit config is read from Django settings:
  - SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW (default 5)
  - SLACK_PR_BOT_COMMENTS_WINDOW_SECONDS  (default 3600)
"""

import time
from typing import Optional

from django.conf import settings

from slack_event_handler.utils.state import load_state, modify_state

SLOT_BUFFER_SEC = 0.05


def _max_per_window() -> int:
    return int(getattr(settings, "SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW", 5))


def _window_seconds() -> int:
    return int(getattr(settings, "SLACK_PR_BOT_COMMENTS_WINDOW_SECONDS", 3600))


def recent_timestamps_at(
    posted_at: list[float], now: float, window_seconds: int | None = None
) -> list[float]:
    """Returns timestamps still inside the rolling window as of time now."""
    window = window_seconds if window_seconds is not None else _window_seconds()
    cutoff = now - window
    return [ts for ts in posted_at if ts > cutoff]


def compute_delay_at(posted_at: list[float], now: float) -> float:
    """
    Returns seconds to wait from now before the next slot opens,
    or 0.0 if a slot is available right now.
    """
    recent = recent_timestamps_at(posted_at, now)
    if len(recent) < _max_per_window():
        return 0.0
    oldest = min(recent)
    return max(0.0, oldest + _window_seconds() - now + SLOT_BUFFER_SEC)


def compute_delay(posted_at: list[float]) -> float:
    """
    Returns seconds to wait before the next slot opens,
    or 0.0 if a slot is available right now.
    """
    return compute_delay_at(posted_at, time.time())


def try_reserve_slot(team_id: Optional[str] = None) -> bool:
    """
    Atomically check availability and reserve a slot timestamp for this team.

    Returns True if a slot was reserved, False if the rolling window is full.
    """
    now = time.time()
    with modify_state(team_id) as state:
        recent = recent_timestamps_at(state["postedAt"], now)
        if len(recent) >= _max_per_window():
            return False
        state["postedAt"] = recent + [now]
        return True


def wait_and_reserve_slot(team_id: Optional[str] = None) -> None:
    """Blocks until a rate-limit slot is atomically reserved for this team."""
    while not try_reserve_slot(team_id):
        delay = compute_delay(load_state(team_id)["postedAt"])
        if delay > 0:
            time.sleep(delay)


def wait_for_slot(team_id: Optional[str] = None) -> None:
    """Blocks until a slot appears available (does not reserve). Prefer wait_and_reserve_slot."""
    while True:
        state = load_state(team_id)
        delay = compute_delay(state["postedAt"])
        if delay == 0:
            break
        time.sleep(delay)


def record_posted(team_id: Optional[str] = None) -> None:
    """Appends a post timestamp without checking the cap (legacy / test helper)."""
    with modify_state(team_id) as state:
        recent = recent_timestamps_at(state["postedAt"], time.time())
        state["postedAt"] = recent + [time.time()]
