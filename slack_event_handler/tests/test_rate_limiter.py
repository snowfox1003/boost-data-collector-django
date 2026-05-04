"""Tests for slack_event_handler.utils.rate_limiter."""

from unittest.mock import patch

import pytest

from slack_event_handler.utils.rate_limiter import (
    compute_delay_at,
    recent_timestamps_at,
    record_posted,
    wait_for_slot,
)


def test_recent_timestamps_at_filters_by_cutoff():
    now = 1000.0
    posted = [100.0, 500.0, 900.0, 950.0]
    recent = recent_timestamps_at(posted, now, window_seconds=200)
    assert recent == [900.0, 950.0]


def test_compute_delay_at_zero_when_under_cap():
    assert compute_delay_at([], 1000.0) == 0.0
    assert compute_delay_at([999.0], 1000.0) == 0.0


@pytest.mark.django_db
def test_compute_delay_at_positive_when_at_cap(settings):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 2
    settings.SLACK_PR_BOT_COMMENTS_WINDOW_SECONDS = 100
    now = 1000.0
    posted = [990.0, 995.0]
    delay = compute_delay_at(posted, now)
    assert delay > 0


@pytest.mark.django_db
def test_wait_for_slot_breaks_when_delay_zero(settings, monkeypatch):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 5

    calls = {"n": 0}

    def fake_compute(state_list):
        calls["n"] += 1
        return 0.0 if calls["n"] > 1 else 1.0

    sleeps = []

    def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(
        "slack_event_handler.utils.rate_limiter.compute_delay", fake_compute
    )
    monkeypatch.setattr("slack_event_handler.utils.rate_limiter.time.sleep", fake_sleep)

    with patch("slack_event_handler.utils.rate_limiter.load_state") as ls:
        ls.return_value = {"postedAt": [], "queue": []}
        wait_for_slot(None)

    assert sleeps == [1.0]


@pytest.mark.django_db
def test_record_posted_appends_timestamp(settings, tmp_path):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 10

    path = tmp_path / "state.json"

    with patch(
        "slack_event_handler.utils.state._get_state_file_path",
        return_value=str(path),
    ):
        with patch(
            "slack_event_handler.utils.rate_limiter.time.time", return_value=42.0
        ):
            record_posted(None)
        from slack_event_handler.utils.state import load_state

        loaded = load_state(None)
    assert 42.0 in loaded["postedAt"]
